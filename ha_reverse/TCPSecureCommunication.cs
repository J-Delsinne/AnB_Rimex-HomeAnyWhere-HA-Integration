using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using log4net;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom;

public class TCPSecureCommunication : TCPCommunication
{
	public bool _secure = true;

	private byte[] _publicKey;

	private static readonly ILog log = LogManager.GetLogger(MethodBase.GetCurrentMethod().DeclaringType);

	private byte[] _privateKey = new byte[256]
	{
		83, 131, 251, 50, 127, 126, 154, 233, 1, 179,
		127, 128, 6, 207, 57, 38, 111, 93, 37, 91,
		30, 38, 40, 196, 179, 120, 4, 172, 159, 11,
		174, 157, 87, 172, 78, 130, 14, 180, 186, 108,
		39, 56, 10, 113, 155, 225, 247, 253, 20, 204,
		20, 13, 113, 229, 184, 247, 124, 203, 224, 11,
		4, 120, 177, 127, 43, 234, 133, 65, 149, 34,
		24, 238, 6, 255, 121, 19, 38, 211, 8, 16,
		117, 4, 83, 108, 4, 253, 145, 243, 49, 147,
		182, 20, 227, 83, 246, 206, 110, 195, 116, 254,
		206, 98, 1, 189, 141, 17, 38, 57, 10, 116,
		81, 202, 86, 66, 81, 213, 123, 142, 166, 71,
		220, 127, 116, 9, 144, 143, 154, 242, 12, 116,
		129, 100, 16, 13, 100, 206, 84, 181, 120, 129,
		165, 144, 54, 235, 130, 201, 231, 92, 189, 63,
		59, 41, 211, 47, 34, 110, 111, 36, 221, 251,
		221, 152, 0, 29, 75, 130, 206, 18, 209, 51,
		41, 34, 79, 146, 249, 148, 235, 18, 87, 47,
		250, 48, 199, 241, 157, 114, 202, 141, 37, 235,
		44, 61, 227, 251, 204, 188, 84, 17, 83, 37,
		226, 206, 120, 249, 220, 111, 232, 226, 251, 65,
		60, 237, 111, 154, 177, 243, 114, 120, 2, 204,
		145, 61, 32, 127, 190, 233, 83, 212, 251, 255,
		110, 66, 177, 246, 94, 77, 20, 3, 180, 251,
		47, 83, 122, 188, 158, 167, 206, 142, 202, 8,
		196, 123, 25, 161, 43, 127
	};

	private byte[] _privateKey2 = new byte[256]
	{
		12, 116, 129, 100, 16, 13, 100, 206, 84, 181,
		120, 129, 165, 144, 54, 235, 130, 201, 231, 92,
		189, 63, 59, 41, 211, 47, 34, 110, 111, 36,
		221, 251, 221, 152, 0, 29, 75, 130, 206, 18,
		209, 51, 41, 34, 79, 146, 249, 148, 235, 18,
		87, 47, 250, 48, 199, 241, 157, 114, 202, 141,
		37, 235, 44, 61, 227, 251, 204, 188, 84, 17,
		83, 37, 226, 206, 120, 249, 220, 111, 232, 226,
		251, 65, 60, 237, 111, 154, 177, 243, 114, 120,
		2, 204, 145, 61, 32, 127, 190, 233, 83, 212,
		251, 255, 110, 66, 177, 246, 94, 77, 20, 3,
		180, 251, 47, 83, 122, 188, 158, 167, 206, 142,
		202, 8, 196, 123, 25, 161, 43, 127, 83, 131,
		251, 50, 127, 126, 154, 233, 1, 179, 127, 128,
		6, 207, 57, 38, 111, 93, 37, 91, 30, 38,
		40, 196, 179, 120, 4, 172, 159, 11, 174, 157,
		87, 172, 78, 130, 14, 180, 186, 108, 39, 56,
		10, 113, 155, 225, 247, 253, 20, 204, 20, 13,
		113, 229, 184, 247, 124, 203, 224, 11, 4, 120,
		177, 127, 43, 234, 133, 65, 149, 34, 24, 238,
		6, 255, 121, 19, 38, 211, 8, 16, 117, 4,
		83, 108, 4, 253, 145, 243, 49, 147, 182, 20,
		227, 83, 246, 206, 110, 195, 116, 254, 206, 98,
		1, 189, 141, 17, 38, 57, 10, 116, 81, 202,
		86, 66, 81, 213, 123, 142, 166, 71, 220, 127,
		116, 9, 144, 143, 154, 242
	};

	public byte[] SendBytes(byte[] bytes)
	{
		ShowByteLog(bytes, "SendBytes");
		if (_secure)
		{
			int num = 0;
			int i = 0;
			int num2 = 0;
			for (; i < bytes.Length; i++)
			{
				num ^= i;
				num2 = bytes[i];
				if (_publicKey != null)
				{
					if (_publicKey.Length != 0)
					{
						bytes[i] = (byte)(num2 ^ _privateKey[num] ^ _publicKey[num % _publicKey.Length]);
					}
				}
				else
				{
					bytes[i] = (byte)(num2 ^ _privateKey2[num]);
				}
				num = bytes[i];
			}
		}
		return bytes;
	}

	public byte[] SubResponse(byte[] bytes)
	{
		return bytes.Skip(7).Take(128).ToArray();
	}

	public byte[] BytesReceived(byte[] bytes)
	{
		if (_secure)
		{
			int num = 0;
			int i = 0;
			int num2 = 0;
			for (; i < bytes.Length; i++)
			{
				num ^= i;
				num2 = bytes[i];
				if (_publicKey != null)
				{
					if (_publicKey.Length != 0)
					{
						bytes[i] = (byte)(num2 ^ _privateKey[num] ^ _publicKey[num % _publicKey.Length]);
					}
				}
				else
				{
					bytes[i] = (byte)(num2 ^ _privateKey2[num]);
				}
				num = num2;
			}
		}
		ShowByteLog(bytes, "BytesReceived");
		return bytes;
	}

	public void SetPublicKey(byte[] bytes)
	{
		if (bytes == null)
		{
			_publicKey = null;
			return;
		}
		_publicKey = new byte[0];
		List<byte> list = new List<byte>();
		for (int i = 0; i < bytes.Length; i++)
		{
			list.Add(bytes[i]);
		}
		_publicKey = list.ToArray();
	}

	public void ResetPublicKey()
	{
		_publicKey = null;
	}

	private void ShowByteLog(byte[] bytes, [CallerMemberName] string fonctionName = "")
	{
	}
}
