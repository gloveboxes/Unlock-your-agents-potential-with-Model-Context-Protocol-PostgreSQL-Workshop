using Aspire.Hosting.Python;

namespace Aspire.Hosting;

public static class Extensions
{
    public static IResourceBuilder<PythonAppResource> WithPostgres(this IResourceBuilder<PythonAppResource> builder, IResourceBuilder<PostgresDatabaseResource> db)
    {
        builder.WithEnvironment("POSTGRES_HOST", () => db.Resource.Parent.PrimaryEndpoint.Host)
               .WithEnvironment("POSTGRES_PORT", () => db.Resource.Parent.PrimaryEndpoint.Port.ToString())
               .WithEnvironment("POSTGRES_USER", () => db.Resource.Parent.UserNameParameter?.ToString() ?? "postgres")
               .WithEnvironment("POSTGRES_PASSWORD", () => db.Resource.Parent.PasswordParameter.Value)
               .WaitFor(db);

        return builder;
    }
}
