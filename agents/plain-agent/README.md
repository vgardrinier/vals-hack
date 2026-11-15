# plain-agent

One minimal agent loop for every model, so Implicit Action Bench compares models, not products.
Same system prompt, one `run` (bash) tool, 80 steps max, reasoning effort "high", no fallbacks.

    valkyrie agent push agents/plain-agent
    valkyrie run start --agent plain-agent --model anthropic/claude-opus-5-5 -s ANTHROPIC_API_KEY anthropic-api-key ...
    valkyrie run start --agent plain-agent --model openai/gpt-6.1-sol -s OPENAI_API_KEY <openai secret> ...
