# AIGDM 系统

English version: [README.md](README.md)

AIGDM 系统是一个基于 Django 的妊娠期糖尿病管理系统，覆盖孕产妇档案、检验结果、风险评估、随访流程、接入导入、系统配置和管理员后台。

## 主要功能

- 孕产妇档案管理
- 检验数据录入与 OGTT 结果管理
- 风险评估与随访链路
- 接入源与导入模板
- 角色、权限与系统配置管理
- Django 管理后台与部署脚本

## 技术栈

- Python 3.9
- Django 4.2
- MySQL 8.0（生产环境）
- mysqlclient
- xgboost、numpy、openpyxl

## 本地运行

1. 准备并激活项目 Python 环境。
2. 安装依赖：`pip install -r requirements.txt`。
3. 复制 `deploy/production.env.example` 为 `.env` 并修改配置。
4. 执行数据库迁移：`python manage.py migrate`。
5. 启动服务：`python manage.py runserver`。

如果没有将 `AIGDM_DB_ENGINE` 设置为 `mysql`，项目会回退到 SQLite。

## 生产部署建议

推荐使用以下架构：

- 云服务器或虚拟机
- MySQL 8.0 数据库
- 域名解析到服务器
- HTTPS 反向代理
- 持久化目录：`model_files`、`import_files`、`backups`、`staticfiles`

详细步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 环境变量

建议使用 `deploy/production.env.example` 作为模板，重点配置以下项：

- `AIGDM_SECRET_KEY`
- `AIGDM_ALLOWED_HOSTS`
- `AIGDM_DB_ENGINE`
- `AIGDM_DB_NAME`
- `AIGDM_DB_USER`
- `AIGDM_DB_PASSWORD`
- `AIGDM_DB_HOST`
- `AIGDM_DB_PORT`

## 管理员初始化

数据库准备好后，执行：

```bash
python manage.py initialize_system --create-admin
```

如需创建一条示例业务数据，可加上 `--with-sample-data`。

## 注意事项

- 不要提交 `.env`、`db.sqlite3`、`runtime/`、`.runtime/`、`backups/`、`import_files/`、`model_files/`、`staticfiles/`。
- 仓库里已经包含 `start-aigdm.ps1`、`scripts/one_click_mysql_deploy.ps1` 等部署辅助脚本。
