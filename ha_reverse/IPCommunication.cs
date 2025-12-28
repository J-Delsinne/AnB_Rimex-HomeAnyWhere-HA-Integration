using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Home_Anywhere_D.Anb.Ha.Commun.Domain;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.LocksGenerator;
using Home_Anywhere_D.MyEvents;
using Home_Anywhere_D.NetworkToolHelper;
using Home_Anywhere_D.Tools;
using Home_Anywhere_D.Widgets.Output;
using log4net;

namespace Home_Anywhere_D.Anb.Ha.Commun.IPcom;

public class IPCommunication : TCPSecureCommunication, IDisposable
{
	public bool Local = true;

	public KeyboardReceived keyboadStatusChanged;

	public ExoOutputReceived ExooutputReceived;

	public ExoAudioValuesReceived audioStatusResponseCommand;

	public bool AllreadyConnectEltWithThisIp;

	public MapTriComGridNewRowReceived MapTriComGridNewRowReceived;

	public TimeoutOccure timeoutOccureHandler;

	public ConnectionChanged Connectionchanged;

	public static byte[] DataToSend;

	public volatile byte[] Data;

	private static object _lockList = new object();

	private object lockConnect = new object();

	private object lockKeepAlive = new object();

	private object lockDisconnect = new object();

	private object lockListToken = new object();

	private object lockExoAudio = new object();

	private bool _getKeyboardStatusStarted;

	public int timeoutIncrement;

	public bool IsTriCom;

	public string _serialTriCom;

	public bool Connecting;

	public bool IskeepAlive;

	public bool Connected;

	public WidgetIdentity WidgetIdentity;

	protected long[] _exoAudioGettingValues = new long[16];

	public bool _getAudioStatusStarted;

	public bool KeepAliveStarted;

	public bool _getExoStatusStarted;

	public bool disposed;

	public List<WidgetOutput> list;

	public double delay;

	public int currentCountRestartTimerKeyboard;

	public int currentCountRestartTimerExo;

	public int countConnect;

	public bool isConnected;

	public List<CancellationTokenSource> CurrentTokenSource;

	private static readonly ILog log = LogManager.GetLogger(MethodBase.GetCurrentMethod().DeclaringType);

	private PreConfiguration PreConf;

	private bool processing;

	public List<Sender> senders;

	public int ExoAudioNumber;

	public IPCom Configuration { get; set; }

	public int BusNumber { get; set; }

	public IPCommunication(IPCom ipcom, int busNumber)
	{
		Configuration = ipcom;
		BusNumber = busNumber;
		Inizialize();
	}

	private void Inizialize()
	{
		CurrentTokenSource = new List<CancellationTokenSource>();
		ClearAppPreconfigurationCollection();
		senders = new List<Sender>();
		if (Configuration is TriCom)
		{
			IsTriCom = true;
		}
		list = new List<WidgetOutput>();
		string text = ((BusNumber == 1) ? Configuration.Bus1 : Configuration.Bus2);
		_synchronousBus = text != "Minido";
		delay = 350.0;
		countConnect = 0;
		disposed = false;
		KeepAliveStarted = false;
		_getAudioStatusStarted = false;
		_getExoStatusStarted = false;
		_getKeyboardStatusStarted = false;
		currentCountRestartTimerKeyboard = 0;
		currentCountRestartTimerExo = 0;
		base.KeepAliveCounter = 0;
		StartAllEvent();
		processing = false;
	}

	private void StartAllEvent()
	{
		Connectionchanged = new ConnectionChanged("exo", local: false);
		ExooutputReceived = new ExoOutputReceived(null);
		keyboadStatusChanged = new KeyboardReceived();
		audioStatusResponseCommand = new ExoAudioValuesReceived();
		CurrentTokenSource = new List<CancellationTokenSource>();
		timeoutOccureHandler = new TimeoutOccure();
	}

	private void KeepAlive(CancellationTokenSource KeepAliveTokenSource)
	{
		lock (lockKeepAlive)
		{
			KeepAliveTokenSource = new CancellationTokenSource();
			CurrentTokenSource.Add(KeepAliveTokenSource);
			CancellationToken token = KeepAliveTokenSource.Token;
			Task.Run(delegate
			{
				bool flag = !KeepAliveTokenSource.IsCancellationRequested;
				bool flag2 = _socket != null && _socket.Connected;
				while (flag2 && flag && !disposed)
				{
					flag = !KeepAliveTokenSource.IsCancellationRequested;
					flag2 = _socket != null && _socket.Connected;
					if (!(flag2 && flag) || disposed)
					{
						Disconnect();
						break;
					}
					try
					{
						int keepAliveCounter = base.KeepAliveCounter;
						base.KeepAliveCounter = keepAliveCounter + 1;
						Task.Delay(TimeSpan.FromMilliseconds(30000.0), token).Wait(token);
						if (!processing)
						{
							SendCommand(SendBytes(new KeepAliveRequestCommand().ToBytes()), KeepAliveResponded);
						}
					}
					catch (OperationCanceledException)
					{
						Disconnect();
						break;
					}
				}
			}, token);
		}
	}

	private void KeepAliveResponded(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command response)
	{
		base.KeepAliveCounter = 0;
	}

	private void ClearAppPreconfigurationCollection()
	{
		lock (_lockList)
		{
			if (App.PreConfigurationCollection != null)
			{
				App.PreConfigurationCollection.Clear();
			}
		}
	}

	private PreConfiguration AddToAppPreconfigurationCollection()
	{
		lock (_lockList)
		{
			PreConfiguration presocket = GetPresocket();
			if (presocket == null && PreConf == null)
			{
				PreConf = new PreConfiguration
				{
					ID = Configuration.ID,
					SerialNumber = ((Configuration is TriCom triCom) ? triCom.SerialNumber : null),
					Bus = BusNumber
				};
				App.PreConfigurationCollection.Add(PreConf);
				return null;
			}
			return presocket;
		}
	}

	private PreConfiguration GetPresocket()
	{
		lock (_lockList)
		{
			if (Configuration is TriCom)
			{
				return App.PreConfigurationCollection.FirstOrDefault((PreConfiguration s) => s != null && s.ID == Configuration.ID && s.SerialNumber != null && s.SerialNumber == ((TriCom)Configuration).SerialNumber);
			}
			if ((Local && Configuration.IsGiprelayLocal()) || Configuration.IsGiprelayDistant())
			{
				return App.PreConfigurationCollection.FirstOrDefault((PreConfiguration s) => s.ID == Configuration.ID);
			}
			return App.PreConfigurationCollection.FirstOrDefault((PreConfiguration s) => s.ID == Configuration.ID && s.Bus == BusNumber);
		}
	}

	protected void SendPriorityCommand()
	{
		CancellationTokenSource priorCancellationSource = new CancellationTokenSource();
		CurrentTokenSource.Add(priorCancellationSource);
		CancellationToken token = priorCancellationSource.Token;
		Task.Run(delegate
		{
			bool flag = !priorCancellationSource.IsCancellationRequested;
			if (_socket != null)
			{
				_ = _socket.Connected;
			}
			while (flag && !disposed)
			{
				flag = !priorCancellationSource.IsCancellationRequested;
				if (!(_socket != null && _socket.Connected && flag) || disposed)
				{
					Disconnect();
					break;
				}
				try
				{
					if (senders.Count > 0)
					{
						processing = true;
						Sender sender = senders[0];
						processing = true;
						SendCommand(sender.bytes, sender.callBack);
						senders.RemoveAt(0);
						processing = false;
					}
					Task.Delay(TimeSpan.FromMilliseconds(250.0), token).Wait(token);
				}
				catch (OperationCanceledException)
				{
					Disconnect();
					break;
				}
			}
		}, token);
	}

	public void Connect()
	{
		lock (lockConnect)
		{
			if (AddToAppPreconfigurationCollection() != null || disposed)
			{
				return;
			}
			if (Local && NetworkInterfaces.IsLocalAddresseReachable(Configuration.LocalAddress))
			{
				if (Configuration.LocalAddress.IsPingSucced())
				{
					if (!Connected)
					{
						ConnectLocal();
					}
					else if (Connectionchanged != null)
					{
						Connectionchanged.SetStatus = "CONNECTED";
					}
				}
				else if (!Connected)
				{
					ConnectRemote();
				}
				else if (Connectionchanged != null)
				{
					Connectionchanged.SetStatus = "CONNECTED";
				}
			}
			else if (!Connected)
			{
				ConnectRemote();
			}
			else if (Connectionchanged != null)
			{
				Connectionchanged.SetStatus = "CONNECTED";
			}
		}
	}

	private void ConnectLocal()
	{
		_address = Configuration.LocalAddress;
		_port = Configuration.LocalPort;
		Local = true;
		if (!string.IsNullOrEmpty(_address) && _port >= 1)
		{
			Open();
		}
		else
		{
			Local = false;
		}
		if (_socket != null && _socket.Connected)
		{
			ConnectRequestCommand connectRequestCommand = new ConnectRequestCommand(Configuration.Username, Configuration.Password, BusNumber);
			SendConnect(connectRequestCommand.ToBytes());
		}
	}

	private void ConnectRemote()
	{
		_address = Configuration.RemoteAddress;
		_port = Configuration.RemotePort;
		if (IsTriCom)
		{
			_serialTriCom = ((TriCom)Configuration).SerialNumber;
		}
		Local = false;
		if (!string.IsNullOrEmpty(_address) && _port >= 1)
		{
			Open();
		}
		if (_socket != null && _socket.Connected)
		{
			ConnectRequestCommand connectRequestCommand = new ConnectRequestCommand(IsTriCom ? (_serialTriCom + Configuration.Username) : Configuration.Username, Configuration.Password, BusNumber);
			SendConnect(connectRequestCommand.ToBytes());
		}
	}

	private void SendConnect(byte[] ConnectionReqByte)
	{
		countConnect++;
		try
		{
			SendCommand(SendBytes(ConnectionReqByte), ConnectResponded);
		}
		catch (Exception ex)
		{
			log.Info("Connect Command Send exception " + ex.Message);
			Disconnect();
			timeoutOccureHandler?.dispatchEvent();
		}
	}

	private void ConnectResponded(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command response)
	{
		if (response == null || disposed)
		{
			if (Connectionchanged != null)
			{
				Connectionchanged.SetStatus = "BADCREDENTIALS";
			}
			Connected = false;
			countConnect = 0;
			return;
		}
		Connecting = false;
		if (response is NonSecureConnectResponseCommand)
		{
			ClearAppPreconfigurationCollection();
			LockGenerator.Instance.RemoveAll();
			_secure = !_secure;
			countConnect--;
			_socket.Dispose();
			Task.Run(delegate
			{
				Connect();
			});
			return;
		}
		if (((ConnectResponseCommand)response).ConnectionStatus == 1)
		{
			Connected = true;
			countConnect--;
			SetPublicKey(SubResponse(((ConnectResponseCommand)response).PublicKey));
		}
		if (((ConnectResponseCommand)response).ConnectionStatus != 1)
		{
			return;
		}
		countConnect = 0;
		if (!isConnected)
		{
			isConnected = true;
			Task.Run(delegate
			{
				SetKeepAliveTimer();
			});
			if (Connectionchanged != null)
			{
				Connectionchanged.SetStatus = "CONNECTED";
			}
		}
	}

	public void Disconnect()
	{
		lock (lockDisconnect)
		{
			StopCurrentThread();
			if (_socket != null)
			{
				if (_socket.Connected)
				{
					SendDisconnectCommand(SendBytes(new DisconnectRequestCommand().ToBytes()));
				}
				DisconnectResponded();
				LockGenerator.Instance.RemoveAll();
			}
		}
	}

	protected void DisconnectResponded()
	{
		Close();
		SetPublicKey(null);
		RemoveIpcomPreconfiguration();
		Connecting = (Connected = (isConnected = (processing = false)));
	}

	private void StopCurrentThread()
	{
		lock (lockListToken)
		{
			KeepAliveStarted = false;
			_getExoStatusStarted = false;
			_getKeyboardStatusStarted = false;
			if (CurrentTokenSource != null && CurrentTokenSource.Count > 0)
			{
				foreach (CancellationTokenSource item in CurrentTokenSource)
				{
					if (item != null)
					{
						if (!item.IsCancellationRequested)
						{
							item.Cancel();
						}
						item.Dispose();
					}
				}
				CurrentTokenSource.Clear();
			}
			RemoveIpcomPreconfiguration();
		}
	}

	private void RemoveIpcomPreconfiguration()
	{
		if (PreConf != null)
		{
			App.PreConfigurationCollection.Remove(PreConf);
		}
		PreConf = null;
	}

	private void StopTricomStatus(CancellationTokenSource tokenSource)
	{
		if (!tokenSource.IsCancellationRequested)
		{
			tokenSource.Cancel();
		}
		tokenSource.Dispose();
	}

	protected override void OnCommandReceived(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command command)
	{
		base.OnCommandReceived(command);
	}

	public async void StartGetKeyboardStatus()
	{
		if (!_getKeyboardStatusStarted)
		{
			await Task.Run(delegate
			{
				_getKeyboardStatusStarted = true;
				GetKeyboardStatus();
			});
		}
	}

	protected void GetKeyboardStatus()
	{
		if (disposed)
		{
			return;
		}
		CancellationTokenSource keyboardCancellationSource = new CancellationTokenSource();
		CurrentTokenSource.Add(keyboardCancellationSource);
		CancellationToken token = keyboardCancellationSource.Token;
		Task.Run(delegate
		{
			bool flag = !keyboardCancellationSource.IsCancellationRequested;
			if (_socket != null)
			{
				_ = _socket.Connected;
			}
			while (flag && !disposed)
			{
				flag = !keyboardCancellationSource.IsCancellationRequested;
				if (!(_socket != null && _socket.Connected && flag) || disposed)
				{
					Disconnect();
					break;
				}
				try
				{
					if (!processing)
					{
						byte[] cmdbyte = SendBytes(new KeyboardStatusRequestCommand().ToBytes());
						currentCountRestartTimerKeyboard++;
						SendCommand(cmdbyte, KeyboardStatusResponded);
					}
					Task.Delay(TimeSpan.FromMilliseconds(delay + 125.0), token).Wait(token);
				}
				catch (OperationCanceledException)
				{
					Disconnect();
					break;
				}
			}
		}, token);
	}

	public void KeyboardStatusResponded(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command response)
	{
		try
		{
			currentCountRestartTimerKeyboard = 0;
			if (response is KeyboardStatusResponseCommand && keyboadStatusChanged != null)
			{
				keyboadStatusChanged.DispatchEvent = (KeyboardStatusResponseCommand)response;
			}
		}
		catch (Exception)
		{
		}
	}

	public virtual async void StartGetExoStatus()
	{
		if (!_getExoStatusStarted)
		{
			_getExoStatusStarted = true;
			await Task.Run(delegate
			{
				GetExoOutputs();
			});
		}
	}

	protected void GetExoOutputs()
	{
		if (disposed)
		{
			return;
		}
		CancellationTokenSource ExoCancellationSource = new CancellationTokenSource();
		if (CurrentTokenSource == null)
		{
			return;
		}
		CurrentTokenSource.Add(ExoCancellationSource);
		CancellationToken token = ExoCancellationSource.Token;
		Task.Run(delegate
		{
			bool flag = !ExoCancellationSource.IsCancellationRequested;
			if (_socket != null)
			{
				_ = _socket.Connected;
			}
			while (flag && !disposed)
			{
				flag = !ExoCancellationSource.IsCancellationRequested;
				if (!(_socket != null && _socket.Connected && flag) || disposed)
				{
					Disconnect();
					break;
				}
				try
				{
					if (!processing)
					{
						byte[] cmdbyte = SendBytes(new ExoOutputsRequestCommand().ToBytes());
						currentCountRestartTimerExo++;
						SendCommand(cmdbyte, ExoOutputsResponded);
					}
					Task.Delay(TimeSpan.FromMilliseconds(delay), token).Wait(token);
				}
				catch (OperationCanceledException)
				{
					Disconnect();
					break;
				}
			}
		}, token);
	}

	public void ExoOutputsResponded(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command response)
	{
		try
		{
			currentCountRestartTimerExo = 0;
			if (response is ExoOutputsResponseCommand && ExooutputReceived != null)
			{
				ExooutputReceived.DispatchEvent = ((ExoOutputsResponseCommand)response).Outputs;
			}
		}
		catch (Exception)
		{
		}
	}

	public void SetExoAudioValues(int exoAudioNumber, int outputNumber, int sourceNumber, int volume, int balance)
	{
		Task.Run(cancellationToken: new CancellationTokenSource().Token, action: delegate
		{
			lock (lockExoAudio)
			{
				SendFrame(new ExoAudioSetValuesFrame(exoAudioNumber, outputNumber, sourceNumber, volume, balance, BusNumber), ExoAudioResponded);
			}
			Thread.Sleep(1);
		});
	}

	public void SetExoAudioMute(int exoAudioNumber, int outputNumber, bool mute)
	{
		Task.Run(cancellationToken: new CancellationTokenSource().Token, action: delegate
		{
			lock (lockExoAudio)
			{
				SendFrame(new ExoAudioSetMuteFrame(exoAudioNumber, outputNumber, mute ? 1 : 0, BusNumber), ExoAudioResponded);
			}
			Thread.Sleep(1);
		});
	}

	private void GetExoAudioValues(int exoAudioNumber)
	{
		SendFrame(new ExoAudioGetValuesFrame(exoAudioNumber, BusNumber), ExoAudioResponded);
	}

	private void ExoAudioResponded(Home_Anywhere_D.Anb.Ha.Commun.IPcom.Command.Command response)
	{
		if (response is FrameResponseCommand frameResponseCommand)
		{
			if (frameResponseCommand.IsAcknowledgement)
			{
				DataReceived(new CancellationTokenSource(), ExoAudioResponded);
			}
			else if (audioStatusResponseCommand != null)
			{
				new AudioStatusResponseCommand(frameResponseCommand, audioStatusResponseCommand);
			}
		}
	}

	private void SetKeepAliveTimer()
	{
		lock (lockKeepAlive)
		{
			if (KeepAliveStarted)
			{
				return;
			}
			KeepAliveStarted = true;
		}
		if (KeepAliveStarted)
		{
			CancellationTokenSource cancellationTokenSource = new CancellationTokenSource();
			CurrentTokenSource.Add(cancellationTokenSource);
			KeepAlive(cancellationTokenSource);
			SendPriorityCommand();
			Task.Delay(200).Wait();
			if (_getAudioStatusStarted)
			{
				GetExoAudioValues(ExoAudioNumber);
			}
		}
	}

	public override void Dispose()
	{
		if (!disposed)
		{
			Connectionchanged = null;
			ExooutputReceived = null;
			keyboadStatusChanged = null;
			audioStatusResponseCommand = null;
			timeoutOccureHandler = null;
			MapTriComGridNewRowReceived = null;
			if (App.instanciedBibusCommunicationList != null)
			{
				App.instanciedBibusCommunicationList.Remove(this);
			}
			IPComManager.removeIpComList(Configuration.ID, BusNumber);
			IPComManager.UpdateIpComList(new BibusCommunication(Configuration, BusNumber));
			RemoveIpcomPreconfiguration();
			Disconnect();
			ResetPublicKey();
			RemoveList();
			base.Dispose();
		}
		disposed = true;
	}

	private void RemoveList()
	{
		if (list != null && list.Count > 0 && Configuration != null)
		{
			WidgetOutput[] array = new WidgetOutput[list.Count];
			list.CopyTo(array, 0);
			WidgetOutput[] array2 = array;
			foreach (WidgetOutput item in array2)
			{
				list.Remove(item);
			}
			if (list.Count > 0)
			{
				RemoveList();
			}
			list.Clear();
		}
	}
}
