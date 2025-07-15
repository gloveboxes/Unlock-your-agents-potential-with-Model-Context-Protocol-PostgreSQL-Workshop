var builder = DistributedApplication.CreateBuilder(args);

var foundry = builder.AddParameter("foundry");
var chatDeployment = builder.AddParameter("chatDeployment");

var pg = builder.AddPostgres("pg")
    .WithPgAdmin()
    .WithInitBindMount(Path.Combine(Environment.CurrentDirectory, "..", "..", "..", "scripts"), isReadOnly: true)
    // Use the pgvector image for PostgreSQL with pgvector extension
    .WithImage("pgvector/pgvector", "pg17")
    // .WithLifetime(ContainerLifetime.Persistent)
    ;

var zava = pg.AddDatabase("zava");

builder.AddUvicornApp("chat-frontend", Path.Combine(Environment.CurrentDirectory, "..", "..", "shared", "chat"), "app:app")
    .WithEnvironment("AZURE_OPENAI_ENDPOINT", foundry)
    .WithEnvironment("AZURE_OPENAI_DEPLOYMENT", chatDeployment);

builder.AddUvicornApp("python-mcp-server", Path.Combine(Environment.CurrentDirectory, "..", "..", "python", "mcp"), "mcp_server:mcp")
    .WithEnvironment("PG_HOST", () => zava.Resource.Parent.PrimaryEndpoint.Host)
    .WithEnvironment("PG_PORT", () => zava.Resource.Parent.PrimaryEndpoint.Port.ToString())
    .WithEnvironment("PG_USER", () => pg.Resource.UserNameParameter?.ToString() ?? "postgres")
    .WithEnvironment("PG_PASSWORD", () => pg.Resource.PasswordParameter.Value)
    ;

builder.Build().Run();
