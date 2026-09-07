# 宫侑 Ombre 的手动删除设置

设置页的「删除需 AI 同意」可独立保存。关闭后，登录用户手动归档或删除时直接执行，不要求理由或 AI 审批。默认仍开启；已有安装不会自动改变行为。

配置键为 `human_deletion_requires_approval`，布尔值 `false` 表示关闭。通过 `/api/config` 保存时使用 `persist: true`，配置写入现有持久卷的 `config.yaml`，不需要环境变量。

切换开关不会执行已有申请；关闭期间不向 AI 展示待审批申请，也不接受旧请求的 AI 审批。申请仍可撤回。直接删除保留现有的删除档案、信件清理和登录验证机制，不做物理清除。

## 更新作者代码

定制提交保留在本 fork 的 `main`。正常使用 GitHub 的 **Sync fork → Update branch** 合并作者更新。出现冲突时保留并调整本功能；不要选择丢弃本 fork 提交或强制重置为上游原版。作者若重构删除流程，更新后需要重新检查本功能。

验证：`python -m pytest tests/test_direct_human_deletion.py tests/test_deletion_requests.py tests/test_human_deletion_web_paths.py tests/test_human_deletion_approval.py tests/test_letter_dashboard_regressions.py tests/test_priority4_confusion_cleanup.py -q`。
