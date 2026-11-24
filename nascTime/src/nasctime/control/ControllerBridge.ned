package nasctime.control;

simple ControllerBridge
{
    parameters:
        bool requireController = default(false);
        int port = default(0);
        int ioTimeoutMs = default(3000);
        double startTime @unit(s) = default(200ms);
        double sampleInterval @unit(s) = default(20ms);
        double stopTime @unit(s) = default(1600ms);
        string policerModule;
        string ranMacModule;
        string priorityQueueModule;
        string backgroundQueueModule;
        string transportShaperModule = default("");
        string prioritySinkModule;
        string backgroundSinkModule;
        string traceFile;
        @class(nasctime::control::ControllerBridge);
}
