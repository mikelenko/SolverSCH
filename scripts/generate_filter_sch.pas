Procedure CreateSolverSCH;
Var
    SchSheet  : ISch_Document;
    Component : ISch_Component;
    Wire      : ISch_Wire;
    Point1, Point2 : TPoint;
Begin
    SchSheet := SchServer.GetActiveSchematicDocument;
    If SchSheet = Nil Then Begin
        ShowMessage('SolverSCH: Open a Schematic Document first!');
        Exit;
    End;

    // Start Undo/Redo registration
    SchServer.ProcessControl.PreProcess(SchSheet, eStore_All);

    // Placing Vin
    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);
    Component.LibReference := 'Source V';
    Component.SourceLibName := 'Miscellaneous Devices.IntLib';
    Component.Designator.Text := 'Vin';
    Component.Location := Point(MilsToCoord(1000), MilsToCoord(5000));
    SchSheet.AddSchObject(Component);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Placing Rfilt
    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);
    Component.LibReference := 'Res1';
    Component.SourceLibName := 'Miscellaneous Devices.IntLib';
    Component.Designator.Text := 'Rfilt';
    Component.Location := Point(MilsToCoord(2200), MilsToCoord(5000));
    SchSheet.AddSchObject(Component);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Placing Cfilt
    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);
    Component.LibReference := 'Cap';
    Component.SourceLibName := 'Miscellaneous Devices.IntLib';
    Component.Designator.Text := 'Cfilt';
    Component.Location := Point(MilsToCoord(3400), MilsToCoord(5000));
    SchSheet.AddSchObject(Component);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Placing Rin
    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);
    Component.LibReference := 'Res1';
    Component.SourceLibName := 'Miscellaneous Devices.IntLib';
    Component.Designator.Text := 'Rin';
    Component.Location := Point(MilsToCoord(4600), MilsToCoord(5000));
    SchSheet.AddSchObject(Component);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Placing Rf
    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);
    Component.LibReference := 'Res1';
    Component.SourceLibName := 'Miscellaneous Devices.IntLib';
    Component.Designator.Text := 'Rf';
    Component.Location := Point(MilsToCoord(5800), MilsToCoord(5000));
    SchSheet.AddSchObject(Component);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Placing U1
    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);
    Component.LibReference := 'OpAmp';
    Component.SourceLibName := 'Miscellaneous Devices.IntLib';
    Component.Designator.Text := 'U1';
    Component.Location := Point(MilsToCoord(1000), MilsToCoord(3800));
    SchSheet.AddSchObject(Component);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Automated Wiring between Nets
    // Net: in
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(1000), MilsToCoord(5100));
    Wire.Location2 := Point(MilsToCoord(2100), MilsToCoord(5000));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    // Net: 0
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(1000), MilsToCoord(4900));
    Wire.Location2 := Point(MilsToCoord(3500), MilsToCoord(5000));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(1000), MilsToCoord(4900));
    Wire.Location2 := Point(MilsToCoord(4700), MilsToCoord(5000));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    // Net: filt_node
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(2300), MilsToCoord(5000));
    Wire.Location2 := Point(MilsToCoord(3300), MilsToCoord(5000));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(2300), MilsToCoord(5000));
    Wire.Location2 := Point(MilsToCoord(800), MilsToCoord(3900));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    // Net: gain_node
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(4500), MilsToCoord(5000));
    Wire.Location2 := Point(MilsToCoord(5700), MilsToCoord(5000));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(4500), MilsToCoord(5000));
    Wire.Location2 := Point(MilsToCoord(800), MilsToCoord(3700));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);
    // Net: out
    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);
    Wire.Location1 := Point(MilsToCoord(5900), MilsToCoord(5000));
    Wire.Location2 := Point(MilsToCoord(1200), MilsToCoord(3800));
    SchSheet.AddSchObject(Wire);
    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);

    // Finalize and Refresh
    SchServer.ProcessControl.PostProcess(SchSheet, eStore_All);
    SchSheet.GraphicallyInvalidate; 
    ShowMessage('SolverSCH: Schematic Generated with ' + IntToStr(SchSheet.SchComponentCount) + ' components and auto-wiring!');
End;