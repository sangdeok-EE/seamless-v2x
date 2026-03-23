# Copyright 2024 ETRI. 
# License-identifier:GNU General Public License v3.0 or later
# yssong00@etri.re.kr

# This program is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published 
# by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
# See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. 
# If not, see <https://www.gnu.org/licenses/>.

""" Sensor Sharing Service Message Structure"""

from socket import *
from scapy.all import *

# TLVC_overall
class TLVC_overall(Packet):

    """ V2X App I/F - Overall Package Structure """
    name = "TLVC_overall"
    fields_desc = [
        IntField("Type", 0),
        ShortField("Length", 0),
        StrFixedLenField("magic_num", b"", length=4), # "EMOP"
        ByteField("version", 0),                      # 1
        ByteField("follow_package_n", 0),             # 2(SSOV + status)
        ShortField("len_follow_packet", 0)
        #ShortField("crc_16", 0)
    ]

# TLVC_Extensible
class TLVC_Extensible(Packet):
    """ V2X App I/F - TLVC Extension Package Structure """
    name = "TLVC_Extensible"
    fields_desc = [
        IntField("Type", 0),        # SSOV = e36e(58222) , Status = (58223)
        ShortField("Length", 0),    # N+2
        StrField("data","")
        #ShortField("crc_16", 0)
    ]

# DB_SSOV (len = 40)
class SSOV(Packet):
    """ V2X App I/F - TLVC Extension -SSOV Package Structure """
    name = "SSOV"
    fields_desc = [
        ShortField("eDeviceType", 1),
        ShortField("eTeleCommType", 1),
        IntField("unDeviceId", 1),
        LongField("ulTimeStamp", 1),
        ShortField("eServiceId", 1),
        ShortField("eActionType", 1),
        ShortField("eRegionId", 1),
        ShortField("ePayloadType", 1),
        ShortField("eCommId", 1),
        ShortField("usDbVer", 1),
        ShortField("usHwVer", 1),
        ShortField("usSwVer", 1),
        IntField("ulPayloadLength", 1),
        IntField("Reserved", 1),
        #IntField("ulPayloadCrc32", 1)
    ]