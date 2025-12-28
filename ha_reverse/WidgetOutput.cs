using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using Home_Anywhere_D.Anb.Commun.MultiLanguage;
using Home_Anywhere_D.Anb.Ha.Commun.Domain;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom;
using Home_Anywhere_D.Anb.Ha.Commun.IPcom.Frame;
using Home_Anywhere_D.Anb.Ha.Commun.Map;
using Home_Anywhere_D.MyEvents;
using Home_Anywhere_D.Widgets.Models;
using SVGImage.SVG;

namespace Home_Anywhere_D.Widgets.Output;

public class WidgetOutput : WidgetDisplayBasic, IDisposable
{
	public IPCommunication _ipcom;

	protected int _exoNumber;

	protected int _outputNumber;

	private byte[] _exoValues;

	public TimeoutOccure timeoutOccureHandler;

	public ConnectionChanged Connectionchanged;

	private CancellationTokenSource tokenSource;

	public WidgetOutputModel widgetOutputModel;

	private CancellationToken token;

	private TimeSpan duration;

	protected DispatcherTimer timer;

	private int l;

	public virtual byte[] ExoValues
	{
		set
		{
			_exoValues = value;
		}
	}

	public byte OutputValue
	{
		get
		{
			if (_exoValues != null && _exoValues.Length != 0)
			{
				return _exoValues[_outputNumber - 1];
			}
			return 0;
		}
		set
		{
			if (_exoValues.Length != 0)
			{
				_exoValues[_outputNumber - 1] = value;
				SendCommandAsync();
			}
		}
	}

	public WidgetOutput(MapElement mapelement = null, MapClip mapclip = null)
		: base(mapelement, mapclip)
	{
		//IL_005f: Unknown result type (might be due to invalid IL or missing references)
		//IL_0069: Expected O, but got Unknown
		App.socketDisconnectHandler.OnSocketDisconnected += SocketDisconnectHandler_OnSocketDisconnected;
		_element = mapelement;
		_mapclip = mapclip;
		Task.Run(delegate
		{
			Refresh();
		});
		_exoValues = new byte[0];
		duration = TimeSpan.FromSeconds(1.0);
		timer = new DispatcherTimer();
		timer.Interval = duration;
		timer.Tick += delegate
		{
			DimmableClick();
		};
		base.MouseLeftButtonDown += WidgetOutput_MouseLeftButtonDown;
		base.MouseLeftButtonUp += WidgetOutput_MouseLeftButtonUp;
		widgetOutputModel = new WidgetOutputModel();
		widgetOutputModel.Title = _element?.Name;
		widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Collapsed;
		widgetOutputModel.SourceNoConnection = "\\Resources\\Output\\wireless-error.svg";
		widgetOutputModel.ControlOpacity = 1.0;
		widgetOutputModel.DisconnectionSource = "\\Resources\\Loading\\loader.gif";
		widgetOutputModel.DisconnectionVisibility = System.Windows.Visibility.Visible;
		widgetOutputModel.ZindexDisconnection = 100;
		tokenSource = new CancellationTokenSource();
		token = tokenSource.Token;
		LoadedDisplay();
		base.DataContext = widgetOutputModel;
	}

	public void LoadedDisplay()
	{
		widgetOutputModel.ZindexOFF = 2;
		widgetOutputModel.ZindexON = 1;
		widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
		widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Visible;
		ThemeImageChanged();
		base.DataContext = widgetOutputModel;
	}

	public override void ThemeImageChanged()
	{
		string text = "/Resources/Output/";
		string graphicType = _element.GraphicType;
		if (graphicType == null)
		{
			return;
		}
		switch (graphicType.Length)
		{
		case 15:
			switch (graphicType[6])
			{
			case 'L':
				if (graphicType == "OutputLightBulb")
				{
					if (_element.Name == "SIRENE" || _element.Name == "BUITEN SIRENE")
					{
						widgetOutputModel.OnSource = text + $"OutputSireneON-{App.LocalSettings.Themes}.svg";
						widgetOutputModel.OffSource = text + $"OutputSireneOFF-{App.LocalSettings.Themes}.svg";
					}
					else
					{
						widgetOutputModel.OffSource = text + $"OutputLightBulbOff-{App.LocalSettings.Themes}.svg";
						widgetOutputModel.OnSource = text + $"OutputLightBulbOn-{App.LocalSettings.Themes}.svg";
					}
				}
				break;
			case 'D':
				if (graphicType == "OutputDoorClose")
				{
					widgetOutputModel.OnSource = text + $"OutputDoorClose-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + string.Format("OutputLocklock.svg", App.LocalSettings.Themes);
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'B':
				if (graphicType == "OutputBlindDown")
				{
					widgetOutputModel.OnSource = text + $"OutputBlindDown-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + $"down-arrow.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'S':
				if (graphicType == "OutputShutterUp")
				{
					widgetOutputModel.OnSource = text + $"OutputShutterUp-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + string.Format("OutputLockOpen.svg", App.LocalSettings.Themes);
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 12:
			switch (graphicType[6])
			{
			case 'H':
				if (graphicType == "OutputHeater")
				{
					widgetOutputModel.OnSource = text + $"OutputHeater-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "thermometer.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'S':
				if (graphicType == "OutputSocket")
				{
					widgetOutputModel.OnSource = text + $"OutputSocket-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
					widgetOutputModel.VisibilityElementON = SVGImage.SVG.Visibility.Visible;
				}
				break;
			case 'B':
				if (graphicType == "OutputBoiler")
				{
					widgetOutputModel.OnSource = text + $"OutputBoiler-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 17:
			switch (graphicType[6])
			{
			case 'W':
				if (graphicType == "OutputWashMachine")
				{
					widgetOutputModel.OnSource = text + $"OutputWashMachine-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'S':
				if (graphicType == "OutputShutterDown")
				{
					widgetOutputModel.OnSource = text + $"OutputShutterDown-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + $"down-arrow.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 21:
			switch (graphicType[6])
			{
			case 'B':
				if (graphicType == "OutputButtonLedYellow")
				{
					widgetOutputModel.OffSource = text + $"OutputButtonLedYellowON-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OnSource = text + $"OutputButtonLedYellowOFF-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'A':
				if (graphicType == "OutputAirConditionner")
				{
					widgetOutputModel.OnSource = text + $"OutputAirConditionner-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 19:
			switch (graphicType[6])
			{
			case 'C':
				if (graphicType == "OutputCoffeeMachine")
				{
					widgetOutputModel.OnSource = text + $"OutputCoffeeMachine-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'M':
				if (graphicType == "OutputMicrowaveOven")
				{
					widgetOutputModel.OnSource = text + $"OutputMicrowaveOven-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + $"lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 16:
			switch (graphicType[6])
			{
			case 'D':
				if (graphicType == "OutputDishWasher")
				{
					widgetOutputModel.OnSource = text + $"OutputDishWasher-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			case 'T':
				if (graphicType == "OutputTelevision")
				{
					widgetOutputModel.OnSource = text + $"OutputTelevision-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 10:
			switch (graphicType[6])
			{
			case 'L':
				if (graphicType == "OutputLock")
				{
					widgetOutputModel.OnSource = text + $"OutputLocklock.svg";
					widgetOutputModel.OffSource = text + $"OutputLockOpen.svg";
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Hidden;
				}
				break;
			case 'O':
				if (graphicType == "OutputOven")
				{
					widgetOutputModel.OnSource = text + $"OutputOven-{App.LocalSettings.Themes}.svg";
					widgetOutputModel.OffSource = text + "lightning.svg";
					widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
					widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
				}
				break;
			}
			break;
		case 13:
			if (graphicType == "OutputBlindUp")
			{
				widgetOutputModel.OnSource = text + $"OutputBlindUp-{App.LocalSettings.Themes}.svg";
				widgetOutputModel.OffSource = text + $"OutputLockOpen.svg";
				widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
				widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
			}
			break;
		case 14:
			if (graphicType == "OutputDoorOpen")
			{
				widgetOutputModel.OnSource = text + $"OutputDoorOpen-{App.LocalSettings.Themes}.svg";
				widgetOutputModel.OffSource = text + string.Format("OutputLockOpen.svg", App.LocalSettings.Themes);
				widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
				widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
			}
			break;
		case 20:
			if (graphicType == "OutputElectricHeater")
			{
				widgetOutputModel.OnSource = text + $"OutputElectricHeater-{App.LocalSettings.Themes}.svg";
				widgetOutputModel.OffSource = text + "lightning.svg";
				widgetOutputModel.VisibilityON = System.Windows.Visibility.Visible;
				widgetOutputModel.VisibilityOFF = System.Windows.Visibility.Hidden;
			}
			break;
		case 23:
			if (graphicType == "OutputLightBulbEconomic")
			{
				widgetOutputModel.OffSource = text + $"OutputLightBulbEconomicOff-{App.LocalSettings.Themes}.svg";
				widgetOutputModel.OnSource = text + $"OutputLightBulbEconomicOn-{App.LocalSettings.Themes}.svg";
			}
			break;
		case 11:
		case 18:
		case 22:
			break;
		}
	}

	private void SocketDisconnectHandler_OnSocketDisconnected(object sender, SocketDisconnectEventArgs e)
	{
	}

	private void DimmableClick()
	{
		timer.Stop();
		OutputModule outputModule = null;
		if (_ipcom != null && _ipcom.Configuration is TriCom)
		{
			outputModule = _element.GetOutputModule(_ipcom.Configuration);
		}
		else if (_ipcom != null)
		{
			outputModule = _element.GetOutputModule(_ipcom.Configuration);
		}
		if (outputModule != null && outputModule.type == "ExoDim" && !_mapclip.DesignMode)
		{
			MultiLanguageBridge multiLanguageBridge = new MultiLanguageBridge("PageHeader");
			mainWindow.SetModal(this, _mapclip, _element, multiLanguageBridge.GetText("ButtonCreate"), multiLanguageBridge.GetText("ButtonCancel"), UiDs.Dimmer);
		}
	}

	protected void WidgetOutput_MouseLeftButtonUp(object sender, MouseButtonEventArgs e)
	{
		if (_mapclip.DesignMode || _ipcom == null || ((_ipcom != null) ? (_ipcom.KeepAliveCounter > 3) : (!_ipcom.Connected)) || l >= 3)
		{
			return;
		}
		base.MouseLeftButtonUp -= WidgetOutput_MouseLeftButtonUp;
		if (this is WidgetOutputDimmable widgetOutputDimmable && this is WidgetOutputDimmableDisplay)
		{
			((object)widgetOutputDimmable).GetType().GetMethod("StopEvent").Invoke(this, null);
		}
		if (timer.IsEnabled && !_mapclip.DesignMode && !(this is WidgetOutputDimmable))
		{
			SwitchValue();
		}
		if (!timer.IsEnabled)
		{
			base.MouseLeftButtonUp += WidgetOutput_MouseLeftButtonUp;
			if (this is WidgetOutputDimmable widgetOutputDimmable2)
			{
				if (this is WidgetOutputDimmableDisplay)
				{
					((object)widgetOutputDimmable2).GetType().GetMethod("StartEvent").Invoke(this, null);
				}
				else if (widgetOutputDimmable2._ipcom != null && !widgetOutputDimmable2._ipcom.Connected)
				{
					widgetOutputDimmable2.StartAllEvent();
				}
			}
		}
		timer.Stop();
	}

	protected void WidgetOutput_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
	{
		if (!(sender is DimmingModalPanel))
		{
			timer.Start();
		}
	}

	public virtual void Refresh()
	{
		if (_element == null)
		{
			ShowNoWirless();
		}
		if (_element == null || _element.ElementConfig == null)
		{
			return;
		}
		string[] array = _element.ElementConfig.Split(new char[1] { ',' });
		_exoNumber = Convert.ToInt16(array[1]);
		_outputNumber = Convert.ToInt16(array[2]);
		int id = 0;
		if (_element.ElementID.HasValue)
		{
			id = _element.ElementID.Value;
		}
		_ipcom = IPComManager.GetIPcom(id, Convert.ToInt16(array[0]));
		if (_ipcom != null && !_ipcom.Connected)
		{
			StartAllEvent();
			if (!App.instanciedBibusCommunicationList.Contains(_ipcom))
			{
				App.instanciedBibusCommunicationList.Add(_ipcom);
			}
			Task.Run(delegate
			{
				if (_ipcom != null)
				{
					_ipcom.Connect();
				}
			});
		}
		else if (_ipcom != null)
		{
			StartAllEvent();
			_ipcom.StartGetExoStatus();
		}
	}

	private void StartAllEvent()
	{
		if (_ipcom.timeoutOccureHandler == null)
		{
			_ipcom.timeoutOccureHandler = new TimeoutOccure();
		}
		_ipcom.timeoutOccureHandler.OnTimeOut += TimeoutOccureHandler_OnTimeOut;
		_ipcom.ExooutputReceived.OnOutputReceives += ExooutputReceived_OnStatusChanged;
		_ipcom.Connectionchanged.OnConnectionChanged += Connectionchanged_OnConnectionChanged;
	}

	private async void Connectionchanged_OnConnectionChanged(object sender, ConnectionChangedEventArgs e)
	{
		if (disposed)
		{
			return;
		}
		if (_ipcom == null)
		{
			await Task.Run(delegate
			{
				Refresh();
			});
		}
		else if (_ipcom.Connected)
		{
			await Task.Run(delegate
			{
				_ipcom?.StartGetExoStatus();
			});
		}
		else if (e.Status == "10054" && _ipcom != null)
		{
			ReconnexionIpcom(e);
		}
		if ((_ipcom == null || !_ipcom.Connected) && disposed)
		{
			StopEvent();
		}
		l++;
	}

	private void ReconnexionIpcom(ConnectionChangedEventArgs e)
	{
		if (_ipcom != null)
		{
			Task.Run(delegate
			{
				_ipcom.Connect();
			});
			ShowNoWirless();
		}
	}

	private async void ExooutputReceived_OnStatusChanged(object myObject, ExoOutputReceivedEventArgs e)
	{
		await Task.Run(delegate
		{
			if (Application.Current != null && !disposed)
			{
				if (_element == null)
				{
					((DispatcherObject)Application.Current).Dispatcher.Invoke((Action)delegate
					{
						ShowNoWirless();
					});
				}
				else
				{
					ExoValues = e.Outputs[_exoNumber - 1];
					l = 0;
					if (widgetOutputModel != null)
					{
						widgetOutputModel.ZindexDisconnection = -1;
						widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Collapsed;
						double num = Convert.ToDouble(_exoValues[_outputNumber - 1]);
						widgetOutputModel.DisconnectionVisibility = System.Windows.Visibility.Collapsed;
						WidgetBase.log.Info("Refresh Status exo graphic element = " + _element.GraphicType.ToString() + " and values receive: " + num);
						if (_element?.GraphicType == "OutputLightBulb" || _element?.GraphicType == "OutputLightBulbEconomic")
						{
							if (num == 0.0)
							{
								if (widgetOutputModel != null)
								{
									widgetOutputModel.ZindexON = 1;
									widgetOutputModel.ZindexOFF = 2;
								}
							}
							else if (widgetOutputModel != null)
							{
								widgetOutputModel.ZindexON = 2;
								widgetOutputModel.ZindexOFF = 1;
							}
							if (widgetOutputModel != null)
							{
								widgetOutputModel.ControlOpacity = num / 100.0;
							}
						}
						else if (widgetOutputModel != null)
						{
							widgetOutputModel.ControlOpacity = 1.0;
							if (_element.GraphicType == "OutputLock")
							{
								widgetOutputModel.VisibilityON = ((num == 0.0) ? System.Windows.Visibility.Hidden : System.Windows.Visibility.Visible);
								widgetOutputModel.VisibilityOFF = ((num != 0.0) ? System.Windows.Visibility.Hidden : System.Windows.Visibility.Visible);
							}
							else
							{
								widgetOutputModel.VisibilityOFF = ((num * 1.0 == 0.0) ? System.Windows.Visibility.Hidden : System.Windows.Visibility.Visible);
							}
						}
					}
				}
			}
		});
	}

	public void SwitchValue()
	{
		if (_exoValues == null || _exoValues.Length == 0)
		{
			widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Visible;
			base.DataContext = widgetOutputModel;
			return;
		}
		widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Collapsed;
		if (_exoValues[_outputNumber - 1] == 0)
		{
			OutputValue = byte.MaxValue;
		}
		else
		{
			OutputValue = 0;
		}
	}

	protected void ShowNoWirless()
	{
		if (widgetOutputModel != null)
		{
			if ((_ipcom != null && _ipcom.Connected && _ipcom.KeepAliveCounter > 3) || l > 3)
			{
				widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Visible;
				widgetOutputModel.ZindexDisconnection = 5;
				widgetOutputModel.DisconnectionVisibility = System.Windows.Visibility.Visible;
			}
			else if (l <= 3)
			{
				widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Visible;
				widgetOutputModel.ZindexDisconnection = 5;
				widgetOutputModel.DisconnectionVisibility = System.Windows.Visibility.Visible;
			}
			else
			{
				widgetOutputModel.NoConnectionVisibility = System.Windows.Visibility.Collapsed;
				widgetOutputModel.ZindexDisconnection = -1;
				widgetOutputModel.DisconnectionVisibility = System.Windows.Visibility.Hidden;
			}
		}
	}

	private void TimeoutOccureHandler_OnTimeOut(object sender, TimeoutOccureEventArgs e)
	{
		Task.Run(delegate
		{
			WidgetBase.log.Info("OUTPUT TIMEOUT");
			if (tokenSource.IsCancellationRequested)
			{
				tokenSource.Dispose();
				StopEvent();
				ShowNoWirless();
			}
			else
			{
				ShowNoWirless();
				if (!disposed && _ipcom != null)
				{
					_ipcom.Connect();
					ShowNoWirless();
				}
				l++;
			}
		}, token);
	}

	private void StopEvent()
	{
		App.socketDisconnectHandler.OnSocketDisconnected -= SocketDisconnectHandler_OnSocketDisconnected;
		StopCommunication();
	}

	public override void StopCommunication()
	{
		if (_ipcom != null)
		{
			if (_ipcom.timeoutOccureHandler != null)
			{
				_ipcom.timeoutOccureHandler.OnTimeOut -= TimeoutOccureHandler_OnTimeOut;
			}
			if (_ipcom.ExooutputReceived != null)
			{
				_ipcom.ExooutputReceived.OnOutputReceives -= ExooutputReceived_OnStatusChanged;
			}
			if (_ipcom.Connectionchanged != null)
			{
				_ipcom.Connectionchanged.OnConnectionChanged -= Connectionchanged_OnConnectionChanged;
			}
			_ipcom.Dispose();
			_ipcom = null;
		}
	}

	private async void SendCommandAsync()
	{
		await Task.Run(delegate
		{
			int num = Convert.ToInt32(_element.ElementConfig.Split(",")[0]);
			int num2 = 60;
			num2 = ((num != 1) ? getAdressBus(_ipcom.Configuration.Bus2) : getAdressBus(_ipcom.Configuration.Bus1));
			if ((num == 1 && _ipcom.Configuration.Bus1 == "Minido") || (num == 1 && _ipcom.Configuration is TriCom))
			{
				num = 2;
			}
			_ipcom.SendFrame(new ExoSetValuesFrame(0, Convert.ToByte(num2 + (_exoNumber - 1)), _exoNumber, _exoValues, Convert.ToByte(num)), _ipcom.ExoOutputsResponded);
			if (!(this is WidgetOutputDimmable))
			{
				base.MouseLeftButtonUp += WidgetOutput_MouseLeftButtonUp;
			}
			else
			{
				base.MouseLeftButtonUp -= WidgetOutput_MouseLeftButtonUp;
			}
		});
	}

	private int getAdressBus(string typeOfBus)
	{
		if (typeOfBus == "BiBus")
		{
			return 30;
		}
		return 60;
	}

	public override void Dispose()
	{
		Dispose(disposing: true);
	}

	protected virtual void Dispose(bool disposing)
	{
		if (disposed)
		{
			return;
		}
		if (disposing)
		{
			if (timer != null)
			{
				timer.Stop();
				timer = null;
			}
			StopEvent();
			if (!tokenSource.IsCancellationRequested)
			{
				tokenSource.Cancel();
			}
			tokenSource.Dispose();
			App.instanciedBibusCommunicationList.Clear();
			l = 0;
			widgetOutputModel = null;
			base.DataContext = null;
		}
		base.Dispose();
		disposed = true;
	}
}
