# MOM 知识库

这里放给 Agent 检索的业务资料。第一阶段只做关键词检索，不使用向量库。

没有写进这里、也没有在代码或数据库里查到的规则，助手必须回答“无法确认”，不能凭经验编造。

## 目录

```text
mom_knowledge/
├── business/     业务流程。例如工单创建后下一步是什么
├── operation/    操作步骤。例如怎么报工、怎么领料
├── rules/        业务规则。例如一个工单能不能领料两次
└── glossary.md   术语表
```

## 怎么补

每个文件用 Markdown，第一行写标题。按模块分子目录，例如 `business/work_order/report.md`。

写规则时只记录已经确认的内容，并注明来源（文档、会议、代码类名）。代码实现以项目仓库为准，不要在这里复制大段源码。

项目代码目录和数据库不写在本目录，通过环境变量配置：

```env
MOM_PROJECTS=backend=D:/mom/server;ui=D:/mom/ui
MOM_KNOWLEDGE_ROOT=mom_knowledge
MOM_DB_HOST=
MOM_DB_PORT=3306
MOM_DB_NAME=
MOM_DB_USER=
MOM_DB_PASSWORD=
```

`MOM_PROJECTS` 用分号分隔多项，每项是 `标识=绝对路径`。换一套业务系统时只改配置，不改代码。
