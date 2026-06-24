using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using TraciConnector.Uniluebeck.Itm.Tcpip;

namespace TraciConnector.Protocol
{
    public class Command
    {
        private readonly int id;
        private readonly Storage content;
        public Command(Storage rawStorage)
        {
            int contentLen = rawStorage.ReadUnsignedByte();
            if (contentLen == 0)
                contentLen = rawStorage.ReadInt() - 6;
            else
                contentLen = contentLen - 2;
            id = rawStorage.ReadUnsignedByte();
            short[] buf = new short[contentLen];
            for (int i = 0; i < contentLen; i++)
            {
                buf[i] = (sbyte)rawStorage.ReadUnsignedByte();
            }

            content = new Storage(buf);
        }

        public Command(int id)
        {
            if (id > 255)
                throw new ArgumentException("id should fit in a byte");
            content = new Storage();
            this.id = id;
        }

        public virtual int Id()
        {
            return id;
        }

        public virtual Storage Content()
        {
            return content;
        }

        public virtual void WriteRawTo(Storage out_renamed)
        {
            // Eclipse SUMO tools/traci/connection.py::_sendCmd: the first ubyte is the *total*
            // command size in bytes (including that length byte), then command id, then payload.
            // Legacy SUMO3d used extended form only (leading 0 + 32-bit length), which SUMO 1.x
            // rejects for normal-sized commands → connection drop / "peer shutdown".
            int totalLen = 1 + 1 + content.Size();
            if (totalLen <= 255)
            {
                out_renamed.WriteUnsignedByte(totalLen);
                out_renamed.WriteUnsignedByte(id);
                foreach (Byte b in content.GetStorageList())
                    out_renamed.WriteByte((sbyte)b);
            }
            else
            {
                out_renamed.WriteUnsignedByte(0);
                out_renamed.WriteInt(totalLen + 4);
                out_renamed.WriteUnsignedByte(id);
                foreach (Byte b in content.GetStorageList())
                    out_renamed.WriteByte((sbyte)b);
            }
        }

        public virtual int RawSize()
        {
            int totalLen = 1 + 1 + content.Size();
            if (totalLen <= 255)
                return totalLen;
            return 1 + 4 + 1 + content.Size();
        }
    }
}