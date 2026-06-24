using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using TraciConnector.Tudresden.Sumo.Conf;
using TraciConnector.Uniluebeck.Itm.Tcpip;

namespace TraciConnector.Protocol
{
    public class StatusResponse
    {
        private readonly int id;
        private readonly int result;
        private readonly string description;
        public StatusResponse(int id): this (id, Constants.RTYPE_OK, "")
        {
        }

        public StatusResponse(int id, int result, string description)
        {
            this.id = id;
            this.result = result;
            this.description = description;
        }

        public StatusResponse(Storage packet)
        {
            // Eclipse SUMO tools/traci/connection.py::_sendExact: prefix = !BBB, err = readString()
            // (int32 length + UTF-8). Legacy parsing used a length-prefixed block and US-ASCII, which
            // mis-aligns the buffer and breaks GETVERSION and all other responses.
            packet.ReadUnsignedByte();
            id = packet.ReadUnsignedByte();
            result = packet.ReadUnsignedByte();
            description = packet.ReadStringUTF8();
        }

        public virtual int Id()
        {
            return id;
        }

        public virtual int Result()
        {
            return result;
        }

        public virtual string Description()
        {
            return description;
        }

        public virtual void WriteTo(Storage out_renamed)
        {
            out_renamed.WriteByte(0);
            out_renamed.WriteInt(5 + 1 + 1 + 4 + description.Count());
            out_renamed.WriteByte(id);
            out_renamed.WriteByte(result);
            out_renamed.WriteStringASCII(description);
        }
    }
}