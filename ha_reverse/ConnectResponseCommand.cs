namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;

public class NonSecureConnectResponseCommand : Command
{
	public override void FromBytes(byte[] ByteArray)
	{
		base.FromBytes(ByteArray);
		ID = 1;
	}
}
