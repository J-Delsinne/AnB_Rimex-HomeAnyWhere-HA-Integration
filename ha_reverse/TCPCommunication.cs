using System;
using System.Linq;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.LocksGenerator;
using log4net;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom;

public class TCPCommunication : IDisposable
{
	public delegate void CallbackDelgate(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command command);

	private bool disposed;

	public bool Opened;

	public string _address;

	public int _port;

	protected bool _synchronousBus;

	protected SocketExtended _socket;

	private CancellationTokenSource cts = new CancellationTokenSource();

	private static readonly ILog log = LogManager.GetLogger(MethodBase.GetCurrentMethod().DeclaringType);

	private static object lockOpen = new object();

	public int KeepAliveCounter { get; protected set; }

	public TCPCommunication()
	{
		KeepAliveCounter = 0;
	}

	public void Open()
	{
		lock (lockOpen)
		{
			try
			{
				_socket = new SocketExtended();
				_socket.ConnectedAddress = _address;
				_socket.Connect_TimeOut(_address, _port, TimeSpan.FromMilliseconds(1000.0));
			}
			catch (Exception ex)
			{
				ShowLog("SOCKET EXCEPTION " + ex.Message);
				_socket.Dispose();
				App.PreConfigurationCollection.Clear();
				BibusCommunication obj = (BibusCommunication)Convert.ChangeType(this, typeof(BibusCommunication));
				obj.Disconnect();
				obj.Local = false;
				obj.timeoutOccureHandler?.dispatchEvent();
			}
		}
	}

	protected void Close()
	{
		if (_socket != null && _socket.Connected)
		{
			_socket.Close();
			_socket = null;
		}
		Opened = false;
	}

	private void ProcessCommand()
	{
	}

	protected void SendCommand(byte[] _cmdbyte, CallbackDelgate _commandCallBack)
	{
		_ = cts.Token;
		BibusCommunication bibusCommunication = (BibusCommunication)Convert.ChangeType(this, typeof(BibusCommunication));
		QueuedLock value = LockGenerator.Instance.GetValue(bibusCommunication);
		try
		{
			value.Enter();
			if (_socket != null && _socket.Connected)
			{
				_socket.SendTimeout = 3000;
				ShowLog("send command", _commandCallBack);
				if (_socket != null)
				{
					_socket.Send(_cmdbyte, _cmdbyte.Length, SocketFlags.None);
				}
				DataReceived(cts, _commandCallBack);
			}
		}
		catch (Exception ex)
		{
			App.PreConfigurationCollection.Clear();
			SocketException ex2 = ex as SocketException;
			int num = 10053;
			if (ex2 != null)
			{
				num = ((ExternalException)(object)ex2).ErrorCode;
			}
			ShowLog("SEND EXCEPTION " + ex.Message + " num error: " + num);
			switch (num)
			{
			case 10053:
				bibusCommunication.Disconnect();
				DispatchEventAtGraficComponent(bibusCommunication);
				break;
			case 10060:
				bibusCommunication.Disconnect();
				DispatchEventAtGraficComponent(bibusCommunication);
				break;
			case 10054:
				bibusCommunication.Disconnect();
				bibusCommunication.Connectionchanged.SetStatus = "10054";
				break;
			default:
				bibusCommunication.Disconnect();
				DispatchEventAtGraficComponent(bibusCommunication);
				break;
			}
		}
		finally
		{
			value.Exit();
		}
	}

	private void DispatchEventAtGraficComponent(IPCommunication ip)
	{
		if (ip.timeoutOccureHandler != null && ip.timeoutOccureHandler != null)
		{
			ip.timeoutOccureHandler.dispatchEvent();
		}
	}

	protected void DataReceived(CancellationTokenSource cts, CallbackDelgate _commandCallBack = null)
	{
		int num = 0;
		byte[] array = new byte[8192];
		if (_socket == null)
		{
			return;
		}
		_socket.ReceiveTimeout = 6000;
		BibusCommunication bibusCommunication = (BibusCommunication)Convert.ChangeType(this, typeof(BibusCommunication));
		try
		{
			num = _socket.Receive(array, array.Length, SocketFlags.None);
			ShowLog("receive statut");
		}
		catch (Exception ex)
		{
			App.PreConfigurationCollection.Clear();
			SocketException ex2 = ex as SocketException;
			int num2 = 10053;
			if (ex2 != null)
			{
				num2 = ((ExternalException)(object)ex2).ErrorCode;
			}
			ShowLog("RECEIVE EXCEPTION " + ex.Message + " num error: " + num2);
			switch (num2)
			{
			case 10053:
				bibusCommunication.Disconnect();
				DispatchEventAtGraficComponent(bibusCommunication);
				break;
			case 10060:
				bibusCommunication.Disconnect();
				DispatchEventAtGraficComponent(bibusCommunication);
				break;
			case 10054:
				bibusCommunication.Disconnect();
				bibusCommunication.Connectionchanged.SetStatus = "10054";
				break;
			default:
				bibusCommunication.Disconnect();
				DispatchEventAtGraficComponent(bibusCommunication);
				break;
			}
			return;
		}
		Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command command = ResponseCommandFactory.Create(bibusCommunication.BytesReceived(array.Take(num).ToArray()));
		if (command != null)
		{
			if (command is TriComResponseCommand)
			{
				OnCommandReceived(command);
			}
			_commandCallBack?.Invoke(command);
		}
	}

	protected virtual void OnCommandReceived(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command command)
	{
		if (command is TriComResponseCommand)
		{
			BibusCommunication bibusCommunication = (BibusCommunication)Convert.ChangeType(this, typeof(BibusCommunication));
			if (command is TriComResponseCommand dispatchEvent && bibusCommunication.MapTriComGridNewRowReceived != null)
			{
				bibusCommunication.MapTriComGridNewRowReceived.DispatchEvent = dispatchEvent;
			}
		}
	}

	public void SendFrame(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame.Frame frame, CallbackDelgate commandCallBack = null)
	{
		ShowLog("Add a frame " + frame.ToString());
		BibusCommunication bibusCommunication = (BibusCommunication)Convert.ChangeType(this, typeof(BibusCommunication));
		bibusCommunication.senders.Add(new Sender(bibusCommunication.SendBytes(new FrameRequestCommand(frame).ToBytes()), commandCallBack));
	}

	private void ShowLog(string action, CallbackDelgate call = null)
	{
		BibusCommunication bibusCommunication = (BibusCommunication)Convert.ChangeType(this, typeof(BibusCommunication));
		log.Info("TCPCOMMUNICATION " + action.ToUpper() + " SOCKET: " + _socket?.GetHashCode() + " IPCOM ID: " + bibusCommunication?.Configuration.ID + " BUS: " + bibusCommunication?.BusNumber + ((call == null) ? "" : (", " + call.Method.Name)));
	}

	public virtual void Dispose()
	{
		Dispose(disposing: true);
	}

	protected void SendDisconnectCommand(byte[] cmdByte)
	{
		if (_socket != null && _socket.Connected)
		{
			try
			{
				_socket.SendTimeout = 1000;
				_socket.Send(cmdByte, cmdByte.Length, SocketFlags.None);
			}
			catch (Exception)
			{
			}
		}
	}

	protected virtual void Dispose(bool disposing)
	{
		if (disposed)
		{
			return;
		}
		if (disposing)
		{
			cts.Cancel();
			if (_socket != null && _socket.Connected)
			{
				_socket.Shutdown(SocketShutdown.Both);
				_socket.Dispose();
				_socket = null;
			}
			KeepAliveCounter = 0;
			LockGenerator.Instance.RemoveAll();
		}
		disposed = true;
	}
}
