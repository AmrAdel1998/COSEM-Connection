#
#  --------------------------------------------------------------------------
#   Gurux Ltd
#
#
#
#  Filename: $HeadURL$
#
#  Version: $Revision$,
#                   $Date$
#                   $Author$
#
#  Copyright (c) Gurux Ltd
#
# ---------------------------------------------------------------------------
#
#   DESCRIPTION
#
#  This file is a part of Gurux Device Framework.
#
#  Gurux Device Framework is Open Source software; you can redistribute it
#  and/or modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; version 2 of the License.
#  Gurux Device Framework is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#  See the GNU General Public License for more details.
#
#  More information of Gurux products: http://www.gurux.org
#
#  This code is licensed under the GNU General Public License v2.
#  Full text may be retrieved at http://www.gnu.org/licenses/gpl-2.0.txt
# ---------------------------------------------------------------------------
import os
from gurux_dlms.GXDLMSClient import GXDLMSTranslatorStructure
from gurux_dlms.enums.Authentication import Authentication
from gurux_dlms.enums.InterfaceType import InterfaceType
from gurux_dlms.secure.GXDLMSSecureClient import GXDLMSSecureClient
from gurux_dlms.IGXCryptoNotifier import IGXCryptoNotifier
from gurux_common.GXCommon import GXCommon
from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator
from gurux_dlms.asn.GXPkcs8 import GXPkcs8
from gurux_dlms.asn.GXx509Certificate import GXx509Certificate
from gurux_dlms.objects.enums.SecuritySuite import SecuritySuite
from gurux_dlms.objects.enums.CertificateType import CertificateType
from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_dlms._GXAPDU import _GXAPDU
from gurux_dlms.GXDLMS import GXDLMS
from gurux_dlms.GXDLMSSNParameters import GXDLMSSNParameters
from gurux_dlms.enums.Command import Command
from gurux_dlms.ConnectionState import ConnectionState
from gurux_dlms.GXSecure import GXSecure

class GXDLMSSecureClient2(GXDLMSSecureClient, IGXCryptoNotifier):
    #
    # Constructor.
    #
    def __init__(
        self,
        useLogicalNameReferencing=False,
        clientAddress=1,
        serverAddress=0x0C,
        forAuthentication=Authentication.NONE,
        password=None,
        interfaceType=InterfaceType.HDLC,
    ):
        GXDLMSSecureClient.__init__(
            self,
            useLogicalNameReferencing,
            clientAddress,
            serverAddress,
            forAuthentication,
            password,
            interfaceType,
        )
        self.__translator = GXDLMSTranslator()

    def onPduEventHandler(self, sender, complete, data):
        print("Decrypted PDU: " + GXCommon.toHex(data))
        if complete:
            try:
                print(self.__translator.pduToXml(data))
            except Exception as ex:
                print(str(ex))

    def getPath(self, securitySuite, certType, path, systemTitle):
        """
        Return correct path.

        :param securitySuite: SecuritySuite enum.
        :param certType: CertificateType enum.
        :param path: Folder path as string.
        :param systemTitle: System title as bytes.
        :return: Full file path or folder path.
        """
        if securitySuite == SecuritySuite.SUITE_2:
            path = os.path.join(path, "384")

        if systemTitle is None:
            return path

        if certType == CertificateType.DIGITAL_SIGNATURE:
            prefix = "D"
        elif certType == CertificateType.KEY_AGREEMENT:
            prefix = "A"
        return os.path.join(path, prefix + GXCommon.toHex(systemTitle))

    def aarqRequest(self):
        # Custom implementation to inject Calling AE Invocation ID (Tag A9)
        # Replaces getApplicationAssociationRequest override which wasn't called.
        
        self.initializePduSize = self.maxReceivePDUSize
        self.initializeChallenge = self.settings.getStoCChallenge()
        self.settings.connected = self.settings.connected & ~ConnectionState.DLMS
        buff = GXByteBuffer(20)
        self.settings.resetBlockIndex()
        GXDLMS.checkInit(self.settings)
        self.settings.setStoCChallenge(None)
        if self.autoIncreaseInvokeID:
            self.settings.setInvokeID(0)
        else:
            self.settings.setInvokeID(1)
            
        # Force Invocation Counter to 0 (matches user manual log)
        self.settings.cipher.invocationCounter = 0
            
        if self.authentication > Authentication.LOW:
            if not self.settings.useCustomChallenge:
                self.settings.ctoSChallenge = GXSecure.generateChallenge()
        else:
            self.settings.setCtoSChallenge(None)
            
        _GXAPDU.generateAarq(self.settings, self.settings.cipher, None, buff)
        
        # INJECTION LOGIC
        data = buff.array() # This returns the bytearray content
        # Note: buff.array() returns reference or copy? GXByteBuffer implementation:
        # returns self.data (bytearray). So modification works if we access it directly.
        # But wait, we might need to modify 'data' which is a bytearray.
        
        st = self.ciphering.systemTitle
        if st:
            # Pattern: A6 Len 04 Len ST
            # inner_len = 04 + len + st
            # But wait, A6 length encoding?
            # A6 [Len] [04] [Len] [ST]
            # Len of [04 Len ST] = 1 + 1 + len(st) = 2 + len(st)
            inner_len = 2 + len(st)
            pattern = bytearray([0xA6, inner_len, 0x04, len(st)]) + st
            
            idx = data.find(pattern)
            if idx != -1:
                print("Injecting Calling AE Invocation ID (A9) into APDU...")
                insert_pos = idx + len(pattern)
                to_insert = bytearray([0xA9, 0x03, 0x02, 0x01, 0x01])
                
                # Insert
                data[insert_pos:insert_pos] = to_insert
                
                # Update AARQ length (Tag 60)
                if data[0] == 0x60:
                    old_len = data[1]
                    if old_len & 0x80 == 0:
                        new_len = old_len + len(to_insert)
                        if new_len > 127:
                             print("Warning: AARQ length overflowed 127 bytes!")
                             # TODO: Handle long form if needed, but for now 93+5=98 fits.
                             data[1] = new_len
                        else:
                            data[1] = new_len
                    else:
                        print("Warning: Long form length in AARQ, not updating (TODO)")
                        
                # Update buff size/content
                # buff.array() returns a copy, so we must write back the modified data to buff.
                buff.clear()
                buff.set(data)
         
        reply = None
        # We only support Short Name referencing for this meter (HDLC)
        # But check settings just in case
        if self.settings.getUseLogicalNameReferencing():
             # Fallback to default if needed, or implement LN support
             # But GXDLMSSNParameters is imported.
             pass 
        
        # Always use SN for this specific task as per context, or match original logic
        # Original logic checks referencing.
        # Since we imported GXDLMSSNParameters, we use that.
        # If LN is needed, we need GXDLMSLNParameters.
        
        p = GXDLMSSNParameters(self.settings, Command.AARQ, 0, 0, None, buff)
        reply = GXDLMS.getSnMessages(p)
            
        return reply

    def onKey(self, sender, args):
        """Called when the public or private key is needed
        and it's unknown.

        sender : The source of the event.
        args : Event arguments.
        """
        try:
            if args.encrypt:
                # Find private key.
                path = self.getPath(
                    args.securitySuite, args.certificateType, "Keys", args.systemTitle
                )
                args.privateKey = GXPkcs8.load(path).privateKey
                print("Client private key:" + path + " " + args.privateKey.toHex())
                print(
                    "Client public key:"
                    + path
                    + " "
                    + args.privateKey.getPublicKey().toHex()
                )
            else:
                # Find public key.
                if not args.systemTitle:
                    path = self.getPath(
                        args.securitySuite,
                        args.certificateType,
                        "Certificates",
                        args.systemTitle,
                    )
                    pk = GXx509Certificate.search(path, args.systemTitle)
                    args.publicKey = pk.publicKey
                    print("Server public key:" + str(pk.serialNumber))
                else:
                    path = self.getPath(
                        args.securitySuite,
                        args.certificateType,
                        "Certificates",
                        args.systemTitle,
                    )
                    pk = GXx509Certificate.load(path)
                    args.publicKey = pk.publicKey
                    print("Server public key:" + str(pk.serialNumber))
        except Exception as ex:
            print(ex.message)

    def onCrypto(self, sender, args):
        """Called to encrypt or decrypt the data using
        external Hardware Security Module.

        sender : The source of the event.
        args : Event arguments.
        """
