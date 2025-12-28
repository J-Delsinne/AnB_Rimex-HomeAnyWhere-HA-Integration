using System.Linq;
using System.Text;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;

public class ConnectResponseCommand : Command
{
	public string IPComVersion;

	public int ConnectionStatus;

	public byte[] PublicKey;

	public override void FromBytes(byte[] bytes)
	{
		PublicKey = new byte[0];
		base.FromBytes(bytes);
		if (bytes.Length == 3)
		{
			ConnectionStatus = bytes.ElementAt(0);
			return;
		}
		byte[] array = bytes.Skip(2).Take(4).ToArray();
		IPComVersion = Encoding.UTF8.GetString(array, 0, array.Length);
		ConnectionStatus = bytes.ElementAt(0);
		PublicKey = bytes;
	}
}
