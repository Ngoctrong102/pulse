# Improvement plan

Working notes from architecture review (2026-08). Do not treat as committed roadmap until owner confirms.

## Clarification: kit vs `.pulse/` bloat

After `pulse init`, the host gets a **copy** of `embed/tools/` → `.pulse/tools/`.

So the large Python modules are not only a kit-dev problem — they also live inside every host’s `.pulse/`:

| Path in kit | Same bytes in host |
|---|---|
| `embed/tools/pulse_lib/next_actions.py` (~1035 LOC) | `.pulse/tools/pulse_lib/next_actions.py` |
| `embed/tools/pulse_lib/cleancode.py` (~662) | `.pulse/tools/pulse_lib/cleancode.py` |
| `embed/tools/pulse_lib/__init__.py` (~622) | `.pulse/tools/pulse_lib/__init__.py` |
| `embed/tools/pulse_lib/next_ranking.py` (~507) | `.pulse/tools/pulse_lib/next_ranking.py` |
| `embed/tools/pulse_lib/docs_drift.py` (~490) | `.pulse/tools/pulse_lib/docs_drift.py` |

Rough static footprint today: **~5k LOC / ~190KB** under `.pulse/tools/`, plus **~24KB** `.pulse/cursor/` templates.

### What can bloat inside `.pulse/` over project life

| Area | Growth pattern | Agent risk |
|---|---|---|
| `.pulse/tools/` | Fixed until upgrade/re-init; fat files already present | High if agent reads/edits engine; usually should **not** touch |
| `.pulse/features/*.yaml` | **One file per card** — scales by count, not file size | Low (good design) |
| `.pulse/cleancode/*.yaml` | One module card each | Low |
| `BOARD.md`, `tech-debt.md`, `implementation-phases.md` | Linear with card count | Medium if huge board pasted into prompts |
| `DRIFT.md`, `docs-drift-report.json`, `mismatch-report.json` | Can grow with findings / docs / tags | Medium–high if reports unbounded |
| `.pulse/plugins/` | Host-owned; only grows if team adds plugins | Depends on hosts |

**Verdict:** Cards are split well. The “phình đáng lo” in `.pulse/` is mainly (1) **vendored engine already large**, and (2) **generated reports** if a big repo accumulates many drift/mismatch findings without pruning. Not the feature YAML layout.

---

## Cleanup backlog — thứ có khả năng phình (dọn cho sạch)

Chuẩn bị dọn theo nhóm. Không đụng containment / SoT cards trừ khi owner chốt.

### A. Engine vendored (đã to sẵn trong mọi `.pulse/tools/`)

| Target | ~LOC hôm nay | Cleanup |
|---|---|---|
| `pulse_lib/next_actions.py` | shim ~57 | [x] Tách `prompt_common` / `prompts_explain` / `prompts_next` / `prompts_tag` |
| `pulse_lib/cleancode.py` | ~600 | [x] prompts → `cleancode_prompts.py`; [ ] store/metrics/render tiếp |
| `pulse_lib/__init__.py` | 622 | Registry load/save/validate vs `views_board.py` / id-catalog render |
| `pulse_lib/next_ranking.py` | 507 | Giữ nếu ổn; chặn không nhồi thêm prompt vào đây |
| `pulse_lib/docs_drift.py` | 490 | Tách `analyze` vs `render_md` / `build_prompt`; giữ truncate cứng |
| `pulse-cli/__main__.py` | 374 | Cân nhắc tách `cmd_set` / `cmd_new` nếu phình tiếp |
| Extension `statusBoardPanel.ts` | 1113 | Tách render overview / detail / backlog / cleancode (kit only; không copy vào `.pulse/`) |

Checklist:

- [ ] Split A-targets trong `embed/` rồi `pulse upgrade` / re-init để host nhận bản gọn
- [ ] Rule: module agent hay đụng **≲300–400 LOC**; cấm thêm prompt dài vào file &gt;500

### B. Generated artifacts trong `.pulse/` (phình theo thời gian project)

| File | Ai ghi | Rủi ro | Cleanup chuẩn bị |
|---|---|---|---|
| `mismatch-report.json` (+ `.md` cạnh đó) | `mismatch detect` | Full findings dump mỗi lần chạy | [x] Cap findings trong file on-disk; summary + `truncated: true`; chi tiết chỉ `--verbose` / stdout |
| `docs-drift-report.json` | `drift` / generate hook | JSON full report; MD đã slice `[:60]`/`[:40]` nhưng JSON có thể vẫn dày | [x] Đồng bộ truncate JSON với MD; [ ] optional `drift --summary-only` |
| `DRIFT.md` | drift hook | Dài khi nhiều gap/orphan; vẫn paste vào prompt | [x] Prompt chỉ nhúng summary counts; [ ] Top-N per section + counts (MD) |
| `BOARD.md` | `generate` | Linear theo số card; paste cả board = nặng | [ ] Board compact mode / lane sections; [ ] prompts dùng `next --json` thay vì full BOARD |
| `id-index.md` | `generate` | Linear theo mọi FR/NFR trong `docs/` | [ ] Generate on-demand hoặc cap; không nhét vào agent prompt mặc định |
| `tech-debt.md` | `generate` | Linear backlog | [ ] Open-only view; done cards rút gọn hoặc bỏ khỏi view |
| `clean-code.md` | cleancode hook | Linear theo module | [ ] OK nếu ít module; [ ] stale/dirty-first ordering |
| `implementation-phases.md` | patch STATUS block | File host có thể dài ngoài block | [ ] Chỉ patch block; không khuyến khích paste cả file |

Checklist:

- [ ] Một policy “derived files are summaries”; raw dump chỉ khi flag debug
- [ ] Document: agent/prompt **không** đọc full `*-report.json` trừ khi đang heal/detect có chủ đích
- [ ] (Optional) `.pulse/.gitignore` suggestions cho JSON report cục bộ nếu team không muốn commit bản đầy đủ — **không** auto-edit `.gitignore` (vision)

### C. Cards / data SoT (thường ổn — vẫn liệt kê để theo dõi)

| Area | Khi nào phình | Cleanup |
|---|---|---|
| Single `features/<id>.yaml` | `done`/`remaining`/`evidence` lists quá dài | [ ] Convention: archive done bullets; [ ] validate warn nếu list &gt; N |
| Số lượng card (nhiều file) | Project lớn | OK (một file/card); [ ] `report`/`next` filter; không gộp lại một file |
| `cleancode/<mod>.yaml` | `findings[]` dài | [ ] Drop done finding ids khi set status done; [ ] cap list + pointer sang backlog cards |
| `_meta.yaml` | Không phình | Giữ nguyên; chỉ fix preserve keys (P0) |

### D. Không phải “file phình” nhưng làm agent nặng

| Hiện tượng | Cleanup |
|---|---|
| Prompt builders nhúng quá nhiều context (speckit, full card, full mismatch) | [ ] Prompt slim: counts + top findings + paths; chi tiết `rg`/đọc file theo nhu cầu |
| `next --json` vẫn có legacy `next` + `queue`/`continue` | [ ] Một payload; bỏ field trùng (P1 ranking story) |
| Agent sửa nhầm `.pulse/tools/` | [ ] Skill/rule: chỉ sửa `features/`, `cleancode/`, plugins host — không đụng `tools/` |

### E. Thứ **không** đưa vào cleanup phình

- Containment: không đụng `src/` / `docs/` từ pulse write path
- Gộp cards về một `features.yaml` lớn (đi ngược design hiện tại)
- Xóa engine khỏi `.pulse/` mà chưa có upgrade/pip story thay thế

---

## P0 — correctness / productize (confirm before coding)

- [x] Preserve full `_meta.yaml` on save (`tag_prefix`, `code_roots`, `plugins`, `speckit`, …) — verify intent first
- [x] Extension `registry.ts`: align `featuresDir` / `cleancodeDir` with `.pulse/…` (or dual-discover); watchers already use `.pulse`
- [ ] Package `embed/` so `pip install` + `init` works (or document source-only)
- [x] Regression tests: meta round-trip after `set`/`new`; extension path smoke if applicable

## P1 — maintainability

- [ ] Formal card/meta schema
- [ ] `pulse upgrade` (or version check) for vendored `.pulse/tools`
- [ ] Honest plugin disable for focus/tags **or** document as markers only
- [ ] Fold heal into `pulse_lib` (less sidecar)
- [ ] One ranking story (legacy `next` vs `queue`/`continue`)
- [ ] Cleancode areas not hardcoded to `ios`/`api`

## P2 — file size / agent efficiency

Chi tiết + checklist dọn: **Cleanup backlog** (mục A–D) phía trên. Tóm tắt:

- [x] Split fat `embed/tools/pulse_lib/*` (→ host `.pulse/tools/` sau upgrade) — next_actions + cleancode prompts; còn `__init__` views / panel
- [x] Cap/summary generated reports (`mismatch-report.*`, `docs-drift-report.json`, `DRIFT.md`, …)
- [x] Slim prompts; thin quality-raise rule (guardrails giữ)

## P2 — polish (from earlier review)

- [x] English-first prompts + locale
- [ ] CI: pytest + extension compile
- [ ] Real hooks.json merge / unlink
- [ ] Use or remove `config.json` duplicate of meta

---

## Token / workflow optimize (đã chốt hướng)

**Nguyên tắc:** tối ưu theo kiểu **giảm nhiễu / trùng lặp**, không **bỏ guardrail**.  
Pulse bán độ tin cậy agent (sync card, không done sớm, không auto-heal) — cắt instruction có thể rẻ input token nhưng **tốn thêm vòng sửa sai**.

Flow hiện tại **đủ tốt về JTBD**; lỗ hổng chính là prompt/rules verbose + chỉ agent đọc derived files đầy đủ — không phải sai vòng lặp.

### Trade-off (nhớ khi implement)

| Hướng | Được | Mất / rủi ro |
|---|---|---|
| Slim `next` / `explain` / `tag` prompt | Paste nhẹ, rẻ mỗi turn | Agent thiếu constraint → lệch board / claim done sớm |
| Rule `quality-raise` luôn ngắn; rubric dài chỉ trong skill | Context nền rẻ | Bỏ qua self-check nếu không invoke skill |
| Không bảo đọc full `DRIFT.md` / `*-report.json` | Ít đọc file phình | Bỏ sót drift/tag nếu summary quá mỏng |
| Thu hẹp `untagged-cleanup` / cleancode | Tránh scan cả repo | Hygiene toàn project chậm hơn |
| Cap generated reports | `.pulse/` sạch | Debug sâu cần `--verbose` |
| Giữ prompt dày như hiện tại | Hành vi ổn định hơn | Mỗi Continue đắt token hơn cần thiết |

- [ ] Cap or summarize drift/mismatch reports written into `.pulse/` (avoid unbounded JSON/MD for agent paste)
- [ ] Document: agents should edit **cards** under `.pulse/features/`, not vendored `.pulse/tools/` unless upgrading the kit

### Đáng làm — ROI cao, trade-off thấp

- [x] **Tách always-on vs on-demand**
  - Rule mỏng (3–5 bullet bắt buộc: sync card, không done khi còn mocks/remaining, không auto-heal)
  - Rubric / checklist dài để trong skill; chỉ load khi quality-raise thật sự chạy
  - Ước lượng hiện tại: `quality-raise.mdc` ~2k tok + skill ~2.6k tok nếu cả hai vào context
- [x] **Prompt slim + pointer** (`next` / `explain` / `tag` / drift)
  - Giữ: action, feature id, counts, top-N remaining/mocks, path tới card
  - Bỏ / không dump: cả `done[]`, full evidence prose, full mismatch findings, lặp lại toàn bộ playbook
  - Trỏ agent đọc `.pulse/features/<id>.yaml` khi cần chi tiết — không paste cả board
- [x] **Cap / summary derived files** (khớp Cleanup backlog B)
  - On-disk summary + `truncated`; full chỉ `--verbose` / stdout
  - Prompt **không** bảo “đọc full `docs-drift-report.json`” mặc định — chỉ counts + top findings
- [x] **Spec Kit blocks**: khi `speckit: false`, prompt không còn jargon / playbook Spec Kit (đã có hướng; audit sót)
- [ ] **Tách file engine phình** (Cleanup A) — giúp agent sửa đúng chỗ; gần như không đổi UX user

### Cân nhắc / làm sau

- [ ] `tag --untagged-cleanup` mặc định scoped theo `focus_id` / subset `code_roots` (flag `--all` cho toàn project)
- [ ] Cleancode scan/fix: nhắc giới hạn glob + file budget; tránh “đọc hết module” nếu quá lớn
- [ ] `explain` project: giữ top incomplete nhỏ; findings chỉ critical/warning top-N (đã có một phần)
- [ ] Document: ưu tiên `next --json` / Continuue prompt thay vì paste cả `BOARD.md` vào chat

### Không làm sớm (anti-goals token)

- [ ] ~~Prompt một dòng~~ (“fix checkout” không context card)
- [ ] ~~Bỏ quality gate giữa implement~~
- [ ] ~~Ép agent luôn đọc full BOARD / full mismatch report thay vì summary~~
- [ ] ~~Cắt “đóng vòng”: cập nhật card + generate + detect trước claim done~~

### Đo thành công (khi đã optimize)

- Paste `next --prompt` ngắn rõ rệt nhưng agent vẫn: sửa đúng scope → cập nhật card → `generate` → không heal trừ khi được yêu cầu
- Always-on rules không chiếm hàng nghìn token mỗi turn
- Derived JSON/MD trong `.pulse/` không phình vô hạn theo findings

---

## Explicit non-goals (for now)

- Do not auto-edit host `src/` / `docs/` (tagging stays audit + prompt)
- Do not force product folder layout
- Do not change containment contract without owner sign-off
- Do not strip agent guardrails chỉ để giảm token (xem mục Token / workflow optimize)