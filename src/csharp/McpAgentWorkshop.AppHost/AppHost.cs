using AspireDevTunnels.AppHost.Extensions;

var builder = DistributedApplication.CreateBuilder(args);

var foundry = builder.AddParameter("FoundryEndpoint");
var chatDeployment = builder.AddParameter("ModelDeploymentName");

var pg = builder.AddPostgres("pg")
    .WithPgAdmin()
    .WithInitBindMount(Path.Combine(Environment.CurrentDirectory, "..", "..", "..", "scripts"), isReadOnly: true)
    // Use the pgvector image for PostgreSQL with pgvector extension
    .WithImage("pgvector/pgvector", "pg17")
    // .WithLifetime(ContainerLifetime.Persistent)
    ;

var zava = pg.AddDatabase("zava");

var sourceFolder = Path.Combine(Environment.CurrentDirectory, "..", "..");

string virtualEnvironmentPath = "/usr/local/python/current";

var devtunnel = builder.AddDevTunnel("mcp-devtunnel");

var mcpServer = builder.AddPythonApp("python-mcp-server", Path.Combine(sourceFolder, "python", "mcp_server"), "mcp_server.py", virtualEnvironmentPath: virtualEnvironmentPath)
    .WithPostgres(zava)
    .WithHttpEndpoint(env: "PORT")
    .WithOtlpExporter()
    .WithEnvironment("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true")
    .WithDevTunnel(devtunnel);

var agentApp = builder.AddPythonApp("python-agent-app", Path.Combine(sourceFolder, "python", "workshop"), "app.py", virtualEnvironmentPath: virtualEnvironmentPath)
    .WithHttpEndpoint(env: "PORT")
    .WithHttpHealthCheck("/health")
    .WithEnvironment("PROJECT_ENDPOINT", foundry)
    .WithEnvironment("MODEL_DEPLOYMENT_NAME", chatDeployment)
    .WithPostgres(zava)
    .WithEnvironment("MAP_MCP_FUNCTIONS", "false")
    .WithReference(mcpServer)
    .WaitFor(mcpServer)
    .WaitFor(devtunnel)
    .WithOtlpExporter()
    .WithEnvironment("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true")
    .WithEnvironment("DEV_TUNNEL_URL", () =>
    {
        var endpoint = mcpServer.GetEndpoint("http") ?? throw new InvalidOperationException("MCP Server HTTP endpoint not found.");

        var devTunnelInfo = devtunnel.Resource.GetTunnelDetailsAsync();
        devTunnelInfo.Wait();

        var result = devTunnelInfo.Result;

        var activePort = result.Tunnel.Ports.FirstOrDefault(p => p.PortNumber == endpoint.Port) ?? throw new InvalidOperationException($"No active port found for MCP Server on port {endpoint.Port}.");

        return activePort.PortUri;
    });

builder.AddPythonApp("chat-frontend", Path.Combine(sourceFolder, "shared", "web_app"), "web_app.py", virtualEnvironmentPath: virtualEnvironmentPath)
    .WithReference(agentApp)
    .WaitFor(agentApp)
    .WithHttpEndpoint(env: "PORT")
    .WithOtlpExporter()
    .WithEnvironment("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true");

builder.AddMcpInspector("mcp-inspector")
    .WithReference(mcpServer);

builder.Build().Run();
