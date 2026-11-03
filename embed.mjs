// Optional local multilingual ONNX recall. Model text is data, not instructions.
import { pipeline, AutoTokenizer, env } from '@huggingface/transformers';
import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const local = path.join(root, '.local');
const cache = path.join(local, 'model-cache');
const model = 'Xenova/multilingual-e5-small';
const revision = '761b726dd34fb83930e26aab4e9ac3899aa1fa78';
const onnxSha256 = '4d24e2bc01a447951524466ef533e52944bf48509e6552810bcee1a2711cb02c';
const prepare = process.argv.includes('--prepare');
env.cacheDir = cache;
env.allowRemoteModels = prepare;

async function walk(directory) {
  const files = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const item = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(item));
    else if (entry.isFile()) files.push(item);
  }
  return files;
}

async function sha256(file) {
  const digest = createHash('sha256');
  const handle = await fs.open(file, 'r');
  try { for await (const chunk of handle.createReadStream()) digest.update(chunk); }
  finally { await handle.close().catch(() => {}); }
  return digest.digest('hex');
}

async function main() {
  if (!prepare) {
    const state = JSON.parse(await fs.readFile(path.join(cache, 'ready.json'), 'utf8'));
    if (state.model !== model || state.revision !== revision || state.sha256 !== onnxSha256) {
      throw new Error('本地模型版本记录不匹配，请重新准备模型');
    }
  }
  const embedder = await pipeline('feature-extraction', model, {
    revision, dtype: 'int8', device: 'cpu', cache_dir: cache,
    local_files_only: !prepare,
  });
  // The v4 pipeline registry can omit a tokenizer for older ONNX exports.
  if (typeof embedder.tokenizer !== 'function') {
    embedder.tokenizer = await AutoTokenizer.from_pretrained(path.join(cache, model, revision),
      { local_files_only: true });
  }
  if (prepare) {
    const files = (await walk(cache)).filter(file => path.basename(file) === 'model_int8.onnx');
    if (files.length !== 1 || await sha256(files[0]) !== onnxSha256) {
      throw new Error('ONNX 文件 SHA-256 不匹配，拒绝标记模型可用');
    }
    const state = { model, revision, sha256: onnxSha256, sizeBytes: (await fs.stat(files[0])).size,
      preparedAt: new Date().toISOString(), license: 'MIT (intfloat/multilingual-e5-small)' };
    await fs.writeFile(path.join(cache, 'ready.json'), JSON.stringify(state, null, 2));
    process.stdout.write(JSON.stringify(state) + '\n');
    return;
  }
  let raw = '';
  for await (const chunk of process.stdin) raw += chunk;
  const texts = JSON.parse(raw);
  if (!Array.isArray(texts) || texts.length > 100 || texts.some(x => typeof x !== 'string' || x.length > 2500)) {
    throw new Error('嵌入输入不是有界字符串数组');
  }
  const embeddings = await embedder(texts.map(text => 'passage: ' + text), { pooling: 'mean', normalize: true });
  process.stdout.write(JSON.stringify(embeddings.tolist()) + '\n');
}

main().catch(error => { process.stderr.write(String(error?.stack || error) + '\n'); process.exitCode = 1; });
