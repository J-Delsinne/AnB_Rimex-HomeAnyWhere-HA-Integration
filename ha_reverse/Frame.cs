using System;
using System.Collections.Generic;
using System.Linq;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;

public class Frame
{
	public byte To = 1;

	public byte From;

	public byte Length;

	public byte Bus = 1;

	public byte[] Data;

	public byte Start = 35;

	public Frame(byte from, byte to, byte bus = 0)
	{
		To = to;
		From = from;
		Bus = bus;
	}

	public Frame(int value, byte[] byteArray)
	{
	}

	public virtual string FromBytes(byte[] ByteArray)
	{
		if (ByteArray[0] != 35)
		{
			return "INVALID";
		}
		To = ByteArray[1];
		From = ByteArray[2];
		Length = ByteArray[3];
		Data = new byte[0];
		Data = ByteArray.Skip(4).Take(Length - 1).ToArray();
		if (ByteArray[Data.Length] != ComputeChecksum())
		{
			return "BADCHECKSUM";
		}
		return null;
	}

	public virtual byte[] ToBytes()
	{
		List<byte> list = new List<byte>();
		if (Bus != 0)
		{
			list.Add(Bus);
		}
		list.Add(Start);
		list.Add(To);
		list.Add(From);
		list.Add(Convert.ToByte(Data.Length + 1));
		byte[] data = Data;
		foreach (byte item in data)
		{
			list.Add(item);
		}
		list.Add(ComputeChecksum());
		list.ToArray();
		return list.ToArray();
	}

	public int CommandNumber()
	{
		if (Data.Length == 0)
		{
			return -1;
		}
		return Data[0];
	}

	private byte ComputeChecksum()
	{
		byte b = 0;
		for (int i = 0; i < Data.Length; i++)
		{
			b ^= Data[i];
		}
		return b;
	}
}
