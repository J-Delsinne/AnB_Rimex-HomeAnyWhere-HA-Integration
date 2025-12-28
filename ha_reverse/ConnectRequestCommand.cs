using System;
using System.Text;
using Home_Anywhere_D.Tools;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;

public class ConnectRequestCommand : Command
{
	public string Username;

	public string Password;

	public int BusNumber;

	public int BusLock;

	public ConnectRequestCommand(string username, string password, int busNumber, int busLock = 0)
	{
		ID = 1;
		Version = 2;
		Username = username;
		Password = password;
		BusNumber = busNumber;
		BusLock = busLock;
	}

	public override byte[] ToBytes()
	{
		byte[] source = base.ToBytes();
		byte[] destination = new byte[2]
		{
			Convert.ToByte(BusNumber),
			Convert.ToByte(BusLock)
		};
		byte[] array = new byte[0];
		string text = "";
		while (text.Length < 26 - ("USER:" + Username).Length)
		{
			text += " ";
		}
		array = Encoding.UTF8.GetBytes("USER:" + Username + text);
		byte[] source2 = ToolHelper.MergeArray(source, array);
		text = "";
		array = new byte[0];
		while (text.Length < 26 - ("PWD:" + Password).Length)
		{
			text += " ";
		}
		array = Encoding.UTF8.GetBytes("PWD:" + Password + text);
		return ToolHelper.MergeArray(ToolHelper.MergeArray(source2, array), destination);
	}
}
