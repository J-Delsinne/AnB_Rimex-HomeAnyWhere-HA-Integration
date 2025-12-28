using System.Collections.Generic;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;

internal class ExoSetValuesFrame : Frame
{
	public int ExoNumber;

	public byte[] Values;

	private int _exoNumber;

	public ExoSetValuesFrame(byte from, byte to, int exoNumber, byte[] values, byte busNumber)
		: base(from, to, busNumber)
	{
		ExoNumber = exoNumber;
		Values = values;
	}

	public override byte[] ToBytes()
	{
		List<byte> list = new List<byte>();
		list.Add(1);
		list.AddRange(Values);
		Data = list.ToArray();
		return base.ToBytes();
	}
}
