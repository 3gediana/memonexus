import { pipeline, env } from "@xenova/transformers";

env.cacheDir = "D:/claude code/parseflow-mcp/model-cache";
env.allowRemoteModels = true;
env.allowLocalModels = true;

console.log("开始下载 Xenova/bge-small-zh-v1.5 (~95MB)...");
await pipeline("feature-extraction", "Xenova/bge-small-zh-v1.5");
console.log("下载完成！");
