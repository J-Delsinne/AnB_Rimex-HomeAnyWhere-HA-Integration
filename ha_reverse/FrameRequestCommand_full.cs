using System.Collections.Generic;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;

internal class FrameRequestCommand : Command
{
	public Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame.Frame FrameToSend;

	public FrameRequestCommand(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame.Frame frame)
	{
		ID = 4;
		Version = 1;
		FrameToSend = frame;
	}

	public override byte[] ToBytes()
	{
		List<byte> list = new List<byte>();
		_ = new byte[0];
		list.AddRange(base.ToBytes());
		list.AddRange(FrameToSend.ToBytes());
		return list.ToArray();
	}
}
