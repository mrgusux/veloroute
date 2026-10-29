"""
Universal Provider Registry
============================
50+ providers mapped by their env var prefix → base URL.
All are OpenAI-compatible REST API endpoints.
Custom provider: set MYPROVIDER_API_KEYS + MYPROVIDER_BASE_URL.
"""

PROVIDER_REGISTRY: dict[str, str] = {
    # ── Frontier / Big Cloud ──────────────────────────────────────────────
    "OPENAI":           "https://api.openai.com/v1",
    "AZURE":            "https://{resource}.openai.azure.com/openai",   # needs override
    "ANTHROPIC":        "https://api.anthropic.com/v1",
    "GOOGLE":           "https://generativelanguage.googleapis.com/v1beta/openai",
    "GEMINI":           "https://generativelanguage.googleapis.com/v1beta/openai",
    "VERTEXAI":         "https://us-central1-aiplatform.googleapis.com/v1",
    "AWS_BEDROCK":      "https://bedrock-runtime.us-east-1.amazonaws.com",

    # ── Chinese / Asia ────────────────────────────────────────────────────
    "DEEPSEEK":         "https://api.deepseek.com/v1",
    "QWEN":             "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "DASHSCOPE":        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "MOONSHOT":         "https://api.moonshot.cn/v1",
    "MINIMAX":          "https://api.minimax.chat/v1",
    "ZHIPU":            "https://open.bigmodel.cn/api/paas/v4",
    "BAIDU":            "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop",
    "VOLCANO":          "https://ark.cn-beijing.volces.com/api/v3",
    "XIAOMI":           "https://api.mimo.xiaomi.com/v1",
    "ZAI":              "https://open.bigmodel.cn/api/paas/v4",

    # ── Fast Inference / Aggregators ─────────────────────────────────────
    "GROQ":             "https://api.groq.com/openai/v1",
    "TOGETHER":         "https://api.together.xyz/v1",
    "FIREWORKS":        "https://api.fireworks.ai/inference/v1",
    "ANYSCALE":         "https://api.endpoints.anyscale.com/v1",
    "PERPLEXITY":       "https://api.perplexity.ai",
    "OPENROUTER":       "https://openrouter.ai/api/v1",
    "REPLICATE":        "https://api.replicate.com/v1",
    "DEEPINFRA":        "https://api.deepinfra.com/v1/openai",
    "FEATHERLESS":      "https://api.featherless.ai/v1",
    "NOVITA":           "https://api.novita.ai/v3/openai",
    "CHUTES":           "https://llm.chutes.ai/v1",
    "NSCALE":           "https://inference.api.nscale.com/v1",
    "NEBIUS":           "https://api.studio.nebius.ai/v1",
    "HYPERBOLIC":       "https://api.hyperbolic.xyz/v1",
    "LAMBDA":           "https://api.lambdalabs.com/v1",
    "SAMBANOVA":        "https://api.sambanova.ai/v1",
    "CEREBRAS":         "https://api.cerebras.ai/v1",
    "FRIENDLIAI":       "https://inference.friendli.ai/v1",
    "GALADRIEL":        "https://api.galadriel.com/v1",
    "GMI":              "https://api.gmi.cloud/v1",
    "PUBLICAI":         "https://api.public.ai/v1",
    "COMETAPI":         "https://api.comet.ai/v1",
    "AIML":             "https://api.aimlapi.com/v1",

    # ── Specialized Providers ─────────────────────────────────────────────
    "MISTRAL":          "https://api.mistral.ai/v1",
    "CODESTRAL":        "https://codestral.mistral.ai/v1",
    "COHERE":           "https://api.cohere.com/v1",
    "AI21":             "https://api.ai21.com/studio/v1",
    "NLP_CLOUD":        "https://api.nlpcloud.io/v1",
    "ALEPH_ALPHA":      "https://api.aleph-alpha.com",
    "PREDIBASE":        "https://serving.app.predibase.com",
    "CLARIFAI":         "https://api.clarifai.com/v2",
    "HUGGINGFACE":      "https://api-inference.huggingface.co/models",
    "BASETEN":          "https://model-{model_id}.api.baseten.co/environments/production/predict",
    "GRADIENT":         "https://api.gradient.ai/api",

    # ── Local / Self-Hosted ───────────────────────────────────────────────
    "OLLAMA":           "http://localhost:11434/v1",
    "LM_STUDIO":        "http://localhost:1234/v1",
    "VLLM":             "http://localhost:8000/v1",
    "LLAMAFILE":        "http://localhost:8080/v1",
    "TRITON":           "http://localhost:8001/v2",
    "XINFERENCE":       "http://localhost:9997/v1",
    "DOCKER_MODEL":     "http://localhost:12434/engines/llama.cpp/v1",

    # ── Enterprise / Cloud ────────────────────────────────────────────────
    "DATABRICKS":       "https://{workspace}.azuredatabricks.net/serving-endpoints",
    "SAGEMAKER":        "https://runtime.sagemaker.us-east-1.amazonaws.com",
    "SNOWFLAKE":        "https://{account}.snowflakecomputing.com/api/v2",
    "WATSONX":          "https://us-south.ml.cloud.ibm.com/ml/v1",
    "SAP":              "https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com",
    "OCI":              "https://inference.generativeai.us-chicago-1.oci.customer-oci.com/20231130",
    "CLOUDFLARE":       "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run",
    "HEROKU":           "https://llm.api.heroku.com/v1",
    "OVH":              "https://oai.endpoints.kepler.ai.cloud.ovh.net/api/openai_compat/v1",
    "SCALEWAY":         "https://api.scaleway.ai/v1",
    "DATAROBOT":        "https://app.datarobot.com/api/v2",

    # ── Nvidia ────────────────────────────────────────────────────────────
    "NVIDIA":           "https://integrate.api.nvidia.com/v1",
    "NVIDIA_NIM":       "https://integrate.api.nvidia.com/v1",

    # ── GitHub / Microsoft ────────────────────────────────────────────────
    "GITHUB":           "https://models.inference.ai.azure.com",
    "VERCEL":           "https://ai-gateway.vercel.sh",
    "XAI":              "https://api.x.ai/v1",

    # ── Image Generation ─────────────────────────────────────────────────
    "STABILITY":        "https://api.stability.ai/v1",
    "FAL":              "https://fal.run",
    "RECRAFT":          "https://external.api.recraft.ai/v1",
    "RUNWAYML":         "https://api.dev.runwayml.com/v1",
    "BLACK_FOREST":     "https://api.us1.bfl.ai/v1",
}
