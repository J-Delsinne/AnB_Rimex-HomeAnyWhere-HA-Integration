using System.Collections.Generic;
using System.Linq;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;

public class ExoOutputsResponseCommand : Command
{
	public byte[][] Outputs;

	public ExoOutputsResponseCommand()
	{
		Outputs = new byte[0][];
	}

	public override void FromBytes(byte[] ByteArray)
	{
		base.FromBytes(ByteArray);
		List<byte[]> list = new List<byte[]>();
		for (int i = 0; i < 16; i++)
		{
			_ = new byte[8];
			for (int j = 2; j < 130; j += 8)
			{
				byte[] item = ByteArray.Skip(j).Take(8).ToArray();
				list.Add(item);
			}
		}
		Outputs = list.Take(16).ToArray();
	}
}
