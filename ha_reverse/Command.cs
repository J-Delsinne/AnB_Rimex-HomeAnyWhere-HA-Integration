using System.Linq;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;

public class Command
{
	public byte ID;

	public byte Version;

	public virtual void FromBytes(byte[] byteArray)
	{
		ID = byteArray.ElementAt(0);
		Version = byteArray.ElementAt(1);
	}

	public virtual byte[] ToBytes()
	{
		return new byte[2] { ID, Version };
	}
}
