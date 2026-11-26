package nasctime.simulations.demos.e2e_ladder;

simple RouteController
{
    parameters:
        bool requireController = default(false);
        bool manageResources = default(false);
        string initialPath = default("direct");
        int port = default(0);
        string traceFile;
        double startTime @unit(s) = default(200ms);
        double sampleInterval @unit(s) = default(20ms);
        double stopTime @unit(s) = default(1300ms);
        @class(nasctime::control::RouteController);
}

network Qfi17ControlledLadder extends Qfi17Ladder
{
    submodules:
        routeController: RouteController;
}
