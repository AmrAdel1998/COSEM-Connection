import argparse
import os
import re
import sys
import cv2
import numpy as np
import pandas as pd
from gurux_common.enums import TraceLevel
from gurux_common.io import Parity, StopBits, BaudRate
from gurux_dlms.enums import InterfaceType, Authentication, Security, Standard
from gurux_dlms import GXDLMSClient
from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_serial.GXSerial import GXSerial
from GXDLMSSecureClient2 import GXDLMSSecureClient2
from GXDLMSReader import GXDLMSReader

def _connect(args):
    client = GXDLMSSecureClient2(True)
    client.interfaceType = InterfaceType.HDLC_WITH_MODE_E
    client.useLogicalNameReferencing = True
    client.clientAddress = args.client
    server = GXDLMSClient.getServerAddress(args.logical, args.physical)
    client.serverAddress = server
    client.authentication = getattr(Authentication, args.auth)
    client.ciphering.security = getattr(Security, args.security)
    try:
        client.ciphering.systemTitle = GXByteBuffer.hexToBytes(args.system_title)
    except Exception:
        client.ciphering.systemTitle = args.system_title.encode()
    client.ciphering.blockCipherKey = GXByteBuffer.hexToBytes(args.block_key)
    client.ciphering.authenticationKey = GXByteBuffer.hexToBytes(args.auth_key)
    client.standard = getattr(Standard, args.standard)
    client.useUtc2NormalTime = True
    media = GXSerial(None)
    media.port = args.port
    media.baudRate = BaudRate.BAUD_RATE_300
    media.dataBits = 7
    media.parity = Parity.EVEN
    media.stopBits = StopBits.ONE
    reader = GXDLMSReader(client, media, TraceLevel.INFO, "0.0.43.1.0.255")
    media.open()
    reader.initializeConnection()
    reader.getAssociationView()
    return client, reader, media

def _disconnect(reader, media):
    try:
        if reader:
            reader.close()
        if media and media.isOpen():
            media.close()
    except Exception:
        pass

def _find_obj(client, ln):
    t = ln.strip()
    for obj in client.objects:
        if (obj.logicalName or "").strip() == t:
            return obj
    return None

def _load_cases(path):
    df = pd.read_excel(path)
    cols = [c.strip() for c in df.columns]
    m = {}
    for i, c in enumerate(cols):
        m[c.lower()] = i
    req = ["tc#", "objective", "obis code", "screen number", "preconditions", "test execution steps", "expected result"]
    for r in req:
        if r not in m:
            raise ValueError("Missing column " + r)
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "tc": str(row[cols[m["tc#"]]]).strip(),
            "objective": str(row[cols[m["objective"]]]).strip(),
            "obis": str(row[cols[m["obis code"]]]).strip(),
            "screen": str(row[cols[m["screen number"]]]).strip(),
            "pre": str(row[cols[m["preconditions"]]]).strip(),
            "steps": str(row[cols[m["test execution steps"]]]).strip(),
            "expect": str(row[cols[m["expected result"]]]).strip(),
        })
    return rows

def _read_value(reader, client, ln):
    obj = _find_obj(client, ln)
    if not obj:
        raise ValueError("Object not found " + ln)
    val = reader.read(obj, 2)
    return val

def _list_images(image_dir, screen):
    candidates = []
    if not os.path.isdir(image_dir):
        return candidates
    for f in os.listdir(image_dir):
        p = os.path.join(image_dir, f)
        if os.path.isfile(p):
            s = f.lower()
            if screen.lower() in s or screen.lower().replace(".", "_") in s or screen.lower().replace(".", "") in s:
                candidates.append(p)
    candidates.sort()
    return candidates

def _open_camera(index):
    cap = cv2.VideoCapture(index)
    if not cap or not cap.isOpened():
        raise RuntimeError("Cannot open camera index " + str(index))
    return cap

def _capture_images(cap, count, delay, save_dir, screen):
    imgs = []
    for i in range(count):
        input(f"Show screen {screen} ({i+1}/{count}). Press Enter to capture...")
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        if delay and delay > 0:
            import time as _t
            _t.sleep(delay)
        if save_dir:
            try:
                os.makedirs(save_dir, exist_ok=True)
                fn = os.path.join(save_dir, f"{screen}_{i+1}.png")
                cv2.imwrite(fn, frame)
            except Exception:
                pass
        imgs.append(frame)
    return imgs

def _preprocess(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    b = cv2.GaussianBlur(g, (5, 5), 0)
    _, th = cv2.threshold(b, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th

def _ocr_text(img):
    try:
        import pytesseract
    except Exception:
        raise RuntimeError("pytesseract not available")
    cfg = "--psm 6"
    txt = pytesseract.image_to_string(img, config=cfg)
    return txt.strip()

def _extract_digits(s):
    s = s.replace(",", ".")
    m = re.findall(r"[0-9]+(?:\\.[0-9]+)?", s)
    if not m:
        return ""
    if len(m) == 1:
        return m[0]
    return "".join(m)

def _format_check(expect, s):
    e = expect.lower()
    if "5 integers" in e and "4 decimals" in e:
        if "." not in s:
            return False
        a, b = s.split(".", 1)
        return len(a) == 5 and len(b) >= 4
    if "14-digit" in e or "14 digit" in e:
        d = re.sub(r"\\D", "", s)
        return len(d) >= 14
    return True

def _compare_values(meter_val, vision_val):
    try:
        mv = float(str(meter_val).replace(",", "."))
        vv = float(str(vision_val).replace(",", "."))
        return abs(mv - vv) < 1e-6
    except Exception:
        return str(meter_val).strip() == str(vision_val).strip()

def run(args):
    client, reader, media = None, None, None
    cap = None
    try:
        cases = _load_cases(args.excel)
        client, reader, media = _connect(args)
        results = []
        use_camera = args.camera_index is not None
        if use_camera:
            cap = _open_camera(args.camera_index)
        for tc in cases:
            ln = tc["obis"]
            screen = tc["screen"]
            expect = tc["expect"]
            if use_camera:
                steps = tc["steps"]
                cnt = 2 if ("across 2" in steps.lower() or "2 consecutive" in steps.lower() or "across 2" in expect.lower()) else 1
                imgs = _capture_images(cap, cnt, args.capture_delay, args.save_snaps_dir, screen)
            else:
                imgs = _list_images(args.image_dir, screen)
            if not imgs:
                results.append((tc["tc"], ln, screen, "NO_IMAGES"))
                continue
            texts = []
            for ip in imgs:
                img = ip if isinstance(ip, np.ndarray) else cv2.imread(ip)
                if img is None:
                    continue
                th = _preprocess(img)
                txt = _ocr_text(th)
                texts.append(txt)
            if not texts:
                results.append((tc["tc"], ln, screen, "OCR_FAILED"))
                continue
            joined = " ".join(texts)
            vis_num = _extract_digits(joined)
            if not _format_check(expect, vis_num):
                results.append((tc["tc"], ln, screen, "FORMAT_FAIL"))
                continue
            try:
                meter_val = _read_value(reader, client, ln)
            except Exception:
                results.append((tc["tc"], ln, screen, "NO_OBJECT"))
                continue
            ok = _compare_values(meter_val, vis_num)
            results.append((tc["tc"], ln, screen, "PASS" if ok else "FAIL"))
        for r in results:
            print(r[0], r[1], r[2], r[3])
    finally:
        try:
            if cap:
                cap.release()
        except Exception:
            pass
        _disconnect(reader, media)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--excel", required=True)
    p.add_argument("--image-dir")
    p.add_argument("--camera-index", type=int)
    p.add_argument("--capture-delay", type=float, default=0.0)
    p.add_argument("--save-snaps-dir")
    p.add_argument("--port", default="COM6")
    p.add_argument("--client", type=int, default=1)
    p.add_argument("--logical", type=int, default=1)
    p.add_argument("--physical", type=int, default=18)
    p.add_argument("--auth", default="HIGH_GMAC")
    p.add_argument("--security", default="AUTHENTICATION_ENCRYPTION")
    p.add_argument("--system_title", default="SACSACSA")
    p.add_argument("--block_key", default="7ADF639CA79632FCA3D7810BE6416ABE")
    p.add_argument("--auth_key", default="245D0F1DF31C4380135AC91D4A22023D")
    p.add_argument("--standard", default="ITALY")
    args = p.parse_args()
    run(args)

if __name__ == "__main__":
    main()
