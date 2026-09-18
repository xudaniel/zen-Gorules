# Earth Entry · Alien Immigration Desk

**[Play in English](https://xudaniel.github.io/zen-Gorules/) · [中文版](https://xudaniel.github.io/zen-Gorules/?lang=zh)**

New planet. Same paperwork. Inspect four fictional travelers, change their manifests, and see whether Earth admits them. A poet's pocket black hole, an ambassador's telepathy, and a botanist's unsealed spores make rule precedence visible.

Demo concept, interface, original vector illustrations, and decision model by Daniel Xu. Powered by the upstream [GoRules ZEN](https://github.com/gorules/zen) engine, MIT licensed. This fork's demo uses the published **2.0.2 WebAssembly package**, not a separately modified engine build.

## How it works

- `public/immigration.json` is the portable JSON Decision Model (JDM), editable in a compatible GoRules editor.
- A **collect** decision table reports all matching inspection findings. A **first** table selects the admission outcome, with safety rules preceding diplomatic or cultural status.
- The real Rust/WASM engine evaluates the model in the browser. The interface does not duplicate admission decisions in JavaScript or fall back to simulated verdicts.
- Changing inputs clears the previous result. Reinspect to get a new stamp. The rulebook highlights the matching policy, and the actual engine trace can be viewed or downloaded.
- All characters and rules are fictional; this is a teaching demo, not a real immigration system. Species and home planet are presentation only and do not determine outcomes.
- No analytics, API keys, backend, or submitted traveler data. Static assets are downloaded from the host; manifest processing is local.

## Run and test

Requires Node.js 24 and pnpm 11.19.0.

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm test
pnpm build
pnpm preview
```

The native test suite uses the same model with ZEN 2.0.2. It checks all four scenarios, corrective changes, conflicting hazards, diplomatic precedence, the 30/31-day boundary, validation, and bilingual messages.

## Hosting

GitHub Actions builds and deploys only `dist/` to GitHub Pages. The workflow is scoped to this demo's changes and can also be run manually.

ZEN's threaded WASM requires SharedArrayBuffer and cross-origin isolation. Vite supplies COOP/COEP headers locally. On GitHub Pages, `public/isolation-worker.js` adds these headers to same-origin responses, makes no cache, and reloads the page once on first use. It controls this site's scope only. Use a current browser over HTTPS or localhost; browsers that block service workers or cross-origin isolation display an engine error instead of a fabricated verdict. The engine download is approximately 14 MB uncompressed; a first visit may take a few seconds.

## 中文

**新星球，老规矩。** 在地球第一个外星人入境窗口值班：检查四位虚构旅客，修改申报资料，观察入境决定如何变化。诗人的口袋黑洞、大使的读心能力，以及植物学家的未密封孢子，都由同一份真实规则模型处理。

界面、原创矢量插画与演示规则由 Daniel Xu 制作，底层使用上游 GoRules ZEN 2.0.2 的 Rust/WebAssembly 引擎。先用 collect 决策表收集全部检查结果，再用 first 决策表选择首个匹配的入境规则。所有安全规则优先于外交和文化交流待遇。

支持中英切换、规则手册、命中行高亮和真实执行记录下载。修改资料后旧结果立即失效，需要重新检查。申报数据仅在浏览器处理，无后台、账号或追踪。角色和政策完全虚构，仅用于学习。
