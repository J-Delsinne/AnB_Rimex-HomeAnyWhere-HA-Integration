using System.Threading.Tasks;
using Home_Anywhere_D.Anb.Ha.Commun.Domain;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom;

internal class BibusCommunication : IPCommunication
{
	public BibusCommunication(IPCom ipcom, int busNumber)
		: base(ipcom, busNumber)
	{
	}

	public void KeyboardkeyPress(string key, int busNumber)
	{
		Task.Run(delegate
		{
			SendFrame(new KeyboardKeyPressFrame(key, domo: false, busNumber), base.KeyboardStatusResponded);
		});
	}
}
