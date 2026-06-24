using System;
using System.IO;
using System.Net.Sockets;
using TraciConnector.Protocol;
using TraciConnector.Tudresden.Sumo.Conf;
using TraciConnector.Uniluebeck.Itm.Tcpip;

/// <summary>SUMO 1.x GETVERSION handshake (same wire format as Python traci).</summary>
public static class TraCIHandshake
{
    public static void PerformGetVersion(NetworkStream stream)
    {
        byte cmd = (byte)(Constants.CMD_GETVERSION & 0xFF);
        byte[] packet = { 0x00, 0x00, 0x00, 0x06, 0x02, cmd };
        stream.Write(packet, 0, packet.Length);
        stream.Flush();

        var respMsg = new ResponseMessage(stream);
        var responses = respMsg.Responses();
        if (responses == null || responses.Count == 0)
            throw new InvalidOperationException("Empty TraCI response to GETVERSION.");

        ResponseContainer rc = responses[0];
        StatusResponse st = rc.GetStatus();
        if (st.Result() != Constants.RTYPE_OK)
            throw new InvalidOperationException($"GETVERSION failed: {st.Description()}");

        Command payload = rc.GetResponse();
        if (payload == null || payload.Id() != Constants.CMD_GETVERSION)
            throw new InvalidOperationException("GETVERSION unexpected payload.");
    }
}
