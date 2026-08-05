# PureGamma API 中转站 — 模型安装说明

`api.puregamma.ai` 提供标准 OpenAI-compatible 接口，聚合 DeepSeek、Moonshot (Kimi)、智谱 (GLM) 三家官方 API。

## 前置条件

1. 已在 [app.puregamma.ai](https://app.puregamma.ai) 注册并订阅付费计划（Pro / Max / Enterprise）
2. 在 [app.puregamma.ai/gateway](https://app.puregamma.ai/gateway) 创建 API Key

## 快速开始

API Key 格式：`sk-pg-...`（创建时一次性显示，请立即保存）

Base URL：`https://api.puregamma.ai/v1`

### Python (OpenAI SDK)

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="https://api.puregamma.ai/v1",
)

# 查看可用模型
models = client.models.list()
for m in models.data:
    print(f"  {m.id} — {m.display_name}")

# 对话
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ],
)
print(response.choices[0].message.content)

# 流式输出
stream = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "Write a short poem."}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Node.js / TypeScript

```bash
npm install openai
```

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  baseURL: "https://api.puregamma.ai/v1",
});

const completion = await client.chat.completions.create({
  model: "deepseek-v4-pro",
  messages: [{ role: "user", content: "Hello" }],
});
console.log(completion.choices[0].message.content);
```

```javascript
// CommonJS
const { OpenAI } = require("openai");

const client = new OpenAI({
  apiKey: "sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  baseURL: "https://api.puregamma.ai/v1",
});

client.chat.completions
  .create({
    model: "kimi-k3-max",
    messages: [{ role: "user", content: "Hello" }],
  })
  .then((r) => console.log(r.choices[0].message.content));
```

### curl

```bash
# 列出可用模型
curl -s https://api.puregamma.ai/v1/models \
  -H "Authorization: Bearer sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  | python3 -m json.tool

# 对话
curl -s https://api.puregamma.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "你好，介绍一下自己"}]
  }' | python3 -m json.tool

# 流式对话
curl -s https://api.puregamma.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "model": "glm-5.2",
    "messages": [{"role": "user", "content": "Say hello"}],
    "stream": true
  }'
```

### Go

```go
package main

import (
	"context"
	"fmt"
	"os"

	openai "github.com/sashabaranov/go-openai"
)

func main() {
	config := openai.DefaultConfig("sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
	config.BaseURL = "https://api.puregamma.ai/v1"
	client := openai.NewClientWithConfig(config)

	resp, err := client.CreateChatCompletion(
		context.Background(),
		openai.ChatCompletionRequest{
			Model: "deepseek-v4-pro",
			Messages: []openai.ChatCompletionMessage{
				{Role: "user", Content: "Hello!"},
			},
		},
	)
	if err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
	fmt.Println(resp.Choices[0].Message.Content)
}
```

### Rust

```toml
# Cargo.toml
[dependencies]
async-openai = "0.20"
```

```rust
use async_openai::{Client, config::OpenAIConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config = OpenAIConfig::new()
        .with_api_key("sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        .with_api_base("https://api.puregamma.ai/v1");
    let client = Client::with_config(config);

    let request = async_openai::types::CreateChatCompletionRequestArgs::default()
        .model("deepseek-v4-flash")
        .messages(vec![async_openai::types::ChatCompletionRequestMessage::User(
            async_openai::types::ChatCompletionRequestUserMessageArgs::default()
                .content("Hello from Rust!")
                .build()?,
        )])
        .build()?;

    let response = client.chat().create(request).await?;
    println!("{}", response.choices[0].message.content.unwrap());
    Ok(())
}
```

### LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="deepseek-v4-pro",
    openai_api_key="sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    openai_api_base="https://api.puregamma.ai/v1",
)

response = llm.invoke("Hello, world!")
print(response.content)
```

### Continue.dev (VS Code)

`~/.continue/config.json`:

```json
{
  "models": [
    {
      "title": "DeepSeek V4 Pro (PureGamma)",
      "provider": "openai",
      "model": "deepseek-v4-pro",
      "apiKey": "sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "apiBase": "https://api.puregamma.ai/v1"
    },
    {
      "title": "Kimi K3 Max (PureGamma)",
      "provider": "openai",
      "model": "kimi-k3-max",
      "apiKey": "sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "apiBase": "https://api.puregamma.ai/v1"
    },
    {
      "title": "GLM 5.2 (PureGamma)",
      "provider": "openai",
      "model": "glm-5.2",
      "apiKey": "sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "apiBase": "https://api.puregamma.ai/v1"
    }
  ]
}
```

### Cursor / Windsurf

Settings → Models → Add Model:

| 字段 | 值 |
|------|-----|
| Model Name | `deepseek-v4-pro` / `kimi-k3-max` / `glm-5.2` |
| API Key | `sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Base URL | `https://api.puregamma.ai/v1` |

### Open WebUI

Admin Panel → Settings → Connections → OpenAI API:

```
API Base URL: https://api.puregamma.ai/v1
API Key: sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### LobeChat / NextChat

环境变量：

```bash
OPENAI_API_KEY=sk-pg-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_PROXY_URL=https://api.puregamma.ai/v1
```

---

## 可用模型

| 模型 ID | 名称 | 能力 |
|---------|------|------|
| `deepseek-v4-pro` | DeepSeek V4 Pro | Chat, Streaming, Tools, JSON |
| `deepseek-v4-flash` | DeepSeek V4 Flash | Chat, Streaming, Tools, JSON |
| `kimi-k3-max` | Kimi K3 Max (Moonshot) | Chat, Streaming, Tools, JSON |
| `glm-5.2` | GLM 5.2 (智谱) | Chat, Streaming, Tools, JSON |

模型可用性取决于管理员是否已批准定价并启用对应 Provider。

---

## 费用

- 按实际 token 消耗计费，定价为官方价格 + 30% markup
- 在 [app.puregamma.ai/gateway](https://app.puregamma.ai/gateway) 查看实时消耗仪表盘
- 每月消费上限在用户设置中配置

---

## 支持

- 域名：`api.puregamma.ai`
- 管理面板：[app.puregamma.ai/gateway](https://app.puregamma.ai/gateway)
- 文档：[AI API Gateway](https://github.com/PureGamma-ai/docs/AI_API_GATEWAY.md)
