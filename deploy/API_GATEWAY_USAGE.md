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
    model="deepseek-flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ],
)
print(response.choices[0].message.content)

# 流式输出
stream = client.chat.completions.create(
    model="deepseek-flash",
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
  model: "deepseek-flash",
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
    "model": "deepseek-flash",
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
			Model: "deepseek-flash",
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
        .model("deepseek-flash")
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
    model="deepseek-flash",
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
      "title": "DeepSeek V4.1 Flash (PureGamma)",
      "provider": "openai",
      "model": "deepseek-flash",
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
| Model Name | `deepseek-flash` / `kimi-k3-max` / `glm-5.2` |
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

| 模型 ID | 名称 | 上游模型 ID | 能力 |
|---------|------|-------------|------|
| `deepseek-flash` | DeepSeek V4.1 Flash（默认推荐） | `deepseek-flash` | Chat, Streaming, Tools, JSON, 思考模式, 图像理解 |
| `deepseek-flash` | DeepSeek V4.1 Flash（旧 ID 兼容别名） | `deepseek-flash` | 同上；DeepSeek 已下线旧模型并将该 ID 路由到 V4.1 Flash |
| `deepseek-v4-pro` | DeepSeek V4 Pro | `deepseek-v4-pro` | Chat, Streaming, Tools, JSON；DeepSeek 公告自 2026-09-14 12:00（北京时间）起路由至 V4.1 Flash |
| `kimi-k3-max` | Kimi K3 Max (Moonshot) | `kimi-k3` | Chat, Streaming, Tools, JSON |
| `glm-5.2` | GLM 5.2 (智谱) | `glm-5.2` | Chat, Streaming, Tools, JSON |

模型可用性取决于管理员是否已批准定价并启用对应 Provider。各行由各自官方上游提供服务；指定其他厂商模型不会被静默改派到 DeepSeek。

调用后可通过响应体 `model` 字段核对实际提供服务的模型。

---

## 费用

- 按实际 token 消耗计费，定价为官方价格 + 30% markup
- DeepSeek 官方对 V4.1 Flash 采用峰谷定价：**上表金额为闲时价格，高峰时段（北京时间周一至周五 09:00-12:00、14:00-18:00）为闲时的 2 倍**。价格同步自官方定价页并需管理员审批后生效。
- 在 [app.puregamma.ai/gateway](https://app.puregamma.ai/gateway) 查看实时消耗仪表盘
- 每月消费上限在用户设置中配置

---

## 支持

- 域名：`api.puregamma.ai`
- 管理面板：[app.puregamma.ai/gateway](https://app.puregamma.ai/gateway)
- 文档：[AI API Gateway](https://github.com/PureGamma-ai/docs/AI_API_GATEWAY.md)
