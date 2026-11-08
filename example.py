import os
from veloroute import VeloRoute, RoutingStrategy

# Initialize VeloRoute client
# Automatically loads provider keys from .env or environment variables
client = VeloRoute(
    env_path=".env",
    strategy=RoutingStrategy.PRIORITY,
    # Example fallback mapping: if gpt-4o fails, fall back to claude-3-5-sonnet or gemini-1.5-pro
    fallbacks={
        "gpt-4o": ["claude-3-5-sonnet", "gemini-1.5-pro"],
    },
    auto_trim_context=True,
)

print("VeloRoute client initialized successfully!")
print(f"Active routing strategy: {client.router.strategy}")
print(f"Loaded providers: {client.get_providers()}")
