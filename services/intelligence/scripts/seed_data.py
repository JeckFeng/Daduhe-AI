"""种子数据创建脚本 — 搭建 PostgreSQL schema + 灌入 seed 数据 + Milvus 向量化。

Usage:
    uv run python scripts/seed_data.py          # 完整执行
    uv run python scripts/seed_data.py --verify # 端到端检索验证
"""

# ============================================================
# 种子文档定义
# ============================================================

SEED_DOCUMENTS = [
    {
        "doc_id": "seed-doc-001",
        "doc_type": "规范",
        "title": "DL/T 2628-2023 水电站水工建筑物缺陷管理规范",
        "authors": ["国家能源局"],
        "source_org": "国家能源局",
        "publish_date": "2023-12-28",
        "version": "1.0",
        "language": "zh-CN",
        "file_format": "pdf",
        "file_path": "raw-docs/seed-doc-001.pdf",
        "file_size_bytes": 2410000,
        "permission_level": "internal",
        "tags": ["水电站", "水工建筑物", "缺陷管理", "裂缝", "渗漏"],
        "abstract": "本规范规定了水电站水工建筑物缺陷的分类、检测、评定与处理要求，适用于大、中型水电站水工建筑物的缺陷管理。",
    },
    {
        "doc_id": "seed-doc-002",
        "doc_type": "规范",
        "title": "DL/T 2700-2023 水电站泄水建筑物水力安全评价导则",
        "authors": ["国家能源局"],
        "source_org": "国家能源局",
        "publish_date": "2023-12-28",
        "version": "1.0",
        "language": "zh-CN",
        "file_format": "pdf",
        "file_path": "raw-docs/seed-doc-002.pdf",
        "file_size_bytes": 724000,
        "permission_level": "internal",
        "tags": ["水电站", "泄水建筑物", "水力安全", "消能", "冲刷"],
        "abstract": "本导则规定了水电站泄水建筑物水力安全评价的技术要求和方法，包括泄洪能力复核、消能设施评价、冲刷与淘刷评价等内容。",
    },
]


# ============================================================
# 种子 Chunk 定义 (按 ICD-01 §5 Chunk JSON 结构)
# ============================================================

SEED_CHUNKS = [
    # ---- seed-doc-001: DLT 2628-2023 (10 chunks) ----
    {
        "chunk_id": "seed-chunk-001",
        "doc_id": "seed-doc-001",
        "chunk_index": 1,
        "chunk_text": (
            "5.1 缺陷分类总则\n"
            "水工建筑物缺陷按性质分为结构缺陷、渗流缺陷、材料劣化缺陷和附属设施缺陷四类。"
            "结构缺陷包括裂缝、变形、沉降、滑坡等影响建筑物整体稳定性的缺陷；"
            "渗流缺陷包括渗漏、管涌、流土等涉及渗流安全的缺陷；"
            "材料劣化缺陷包括混凝土碳化、冻融剥蚀、钢筋锈蚀、溶蚀等材料性能退化类缺陷；"
            "附属设施缺陷包括止水失效、排水孔堵塞、监测仪器故障等影响附属功能的缺陷。"
        ),
        "page_number": 18,
        "section_title": "缺陷分类总则",
        "section_number": "5.1",
        "char_start": 4500,
        "char_end": 4750,
        "token_count": 180,
    },
    {
        "chunk_id": "seed-chunk-002",
        "doc_id": "seed-doc-001",
        "chunk_index": 2,
        "chunk_text": (
            "5.2.3 裂缝处理标准\n"
            "混凝土裂缝根据宽度分为三个等级，采取对应处理措施："
            "宽度小于0.2mm为细微裂缝，对结构安全性影响较小，可采用表面封闭法处理，"
            "涂刷环氧涂料或聚合物水泥砂浆进行封闭；宽度在0.2mm至0.3mm之间为中等裂缝，"
            "应采用化学灌浆处理，灌浆材料宜选用低粘度环氧树脂或聚氨酯浆材；"
            "裂缝宽度大于0.3mm判定为较大缺陷，应采取灌浆处理或加固处理，"
            "并应进行专项安全评估。对于贯穿性裂缝和深层裂缝，应优先采用灌浆法；"
            "对于表层裂缝，可采用表面封闭法或凿槽嵌补法。"
        ),
        "page_number": 23,
        "section_title": "裂缝处理标准",
        "section_number": "5.2.3",
        "char_start": 5600,
        "char_end": 5900,
        "token_count": 200,
    },
    {
        "chunk_id": "seed-chunk-003",
        "doc_id": "seed-doc-001",
        "chunk_index": 3,
        "chunk_text": (
            "5.3.1 渗漏量分级标准\n"
            "水工建筑物渗漏按渗漏量大小和危害程度分为三个等级："
            "渗漏量小于0.1L/s为轻微渗漏，可通过日常维护处理，无需专项治理；"
            "渗漏量在0.1L/s至1.0L/s之间为中等渗漏，应进行渗漏原因调查，"
            "根据渗漏类型采取帷幕灌浆、化学灌浆或防渗面板修复等措施；"
            "渗漏量大于1.0L/s或出现浑浊水流时判定为严重渗漏，"
            "应立即启动应急响应，组织专家会诊，查明渗漏通道，优先采用灌浆堵漏，"
            "必要时降低库水位运行。对于接触渗漏和绕坝渗漏，应特别关注渗压变化。"
        ),
        "page_number": 28,
        "section_title": "渗漏量分级标准",
        "section_number": "5.3.1",
        "char_start": 6800,
        "char_end": 7200,
        "token_count": 210,
    },
    {
        "chunk_id": "seed-chunk-004",
        "doc_id": "seed-doc-001",
        "chunk_index": 4,
        "chunk_text": (
            "5.3.2 渗漏处理技术\n"
            "根据不同渗漏类型选择相应的处理技术："
            "坝基渗漏优先采用帷幕灌浆，灌浆孔深度应深入相对不透水层以下不小于5m，"
            "灌浆压力应根据岩体条件经现场试验确定，一般控制在0.3MPa至1.5MPa范围内；"
            "坝体渗漏可采用劈裂灌浆或高压喷射灌浆，灌浆材料选用水泥-水玻璃双液浆或"
            "超细水泥浆液；接触渗漏应在接触面布设灌浆孔，采用低压密孔灌浆，"
            "灌浆压力不超过0.3MPa；伸缩缝止水失效导致的渗漏应重新设置止水结构，"
            "可选用铜止水、橡胶止水或PVC止水带。"
        ),
        "page_number": 30,
        "section_title": "渗漏处理技术",
        "section_number": "5.3.2",
        "char_start": 7200,
        "char_end": 7600,
        "token_count": 220,
    },
    {
        "chunk_id": "seed-chunk-005",
        "doc_id": "seed-doc-001",
        "chunk_index": 5,
        "chunk_text": (
            "5.4.1 混凝土强度检测与评定\n"
            "混凝土强度检测方法包括回弹法、超声-回弹综合法、钻芯法及拔出法。"
            "对于水工建筑物主要承重结构，应优先采用钻芯法进行混凝土抗压强度检测，"
            "芯样直径不宜小于100mm，每组芯样数量不少于3个。当实测混凝土强度低于"
            "设计强度等级的85%时，应评定为强度不足缺陷，需进行结构承载能力复核。"
            "复核可采用有限元数值分析方法，计算时应考虑混凝土的实际强度、配筋率"
            "及荷载组合。对于强度不足区域，可采用增大截面法、外包钢法或粘贴碳纤维"
            "布法进行加固处理。"
        ),
        "page_number": 35,
        "section_title": "混凝土强度检测与评定",
        "section_number": "5.4.1",
        "char_start": 8400,
        "char_end": 8800,
        "token_count": 200,
    },
    {
        "chunk_id": "seed-chunk-006",
        "doc_id": "seed-doc-001",
        "chunk_index": 6,
        "chunk_text": (
            "5.4.3 混凝土碳化深度评定标准\n"
            "混凝土碳化深度采用酚酞试剂法检测，在新鲜劈裂面上喷洒1%酚酞酒精溶液，"
            "未碳化区域呈紫红色，碳化区域不变色。碳化深度评定标准如下："
            "碳化深度小于钢筋保护层厚度的50%为轻度碳化，可表面涂刷防碳化涂料；"
            "碳化深度达到保护层厚度的50%至100%为中度碳化，应采用表面涂层或"
            "电化学再碱化处理；碳化深度超过保护层厚度时为严重碳化，"
            "钢筋已处于碳化区，存在锈蚀风险，应采取电化学脱盐或重建保护层等"
            "综合修复措施。对于处于水位变动区的混凝土结构，碳化速率加快，"
            "检测周期应缩短至3年一次。"
        ),
        "page_number": 40,
        "section_title": "混凝土碳化深度评定标准",
        "section_number": "5.4.3",
        "char_start": 9600,
        "char_end": 10000,
        "token_count": 210,
    },
    {
        "chunk_id": "seed-chunk-007",
        "doc_id": "seed-doc-001",
        "chunk_index": 7,
        "chunk_text": (
            "5.5 金属结构缺陷管理\n"
            "水工金属结构包括闸门、拦污栅、启闭机、压力钢管等。"
            "金属结构缺陷主要包括腐蚀、磨损、变形、疲劳裂纹和连接件松动。"
            "腐蚀深度超过构件原厚度的10%或局部腐蚀坑深度超过3mm时，"
            "应进行除锈防腐处理并评估剩余承载能力。焊缝及热影响区应每5年进行"
            "一次无损检测，优先采用超声波探伤或磁粉探伤。闸门承重构件如主梁、"
            "支臂发现疲劳裂纹，应立即停止运行，进行补焊或更换。"
            "压力钢管壁厚减薄超过设计壁厚的15%时，应进行强度复核，"
            "必要时降低运行水头或进行加固处理。"
        ),
        "page_number": 45,
        "section_title": "金属结构缺陷管理",
        "section_number": "5.5",
        "char_start": 10800,
        "char_end": 11200,
        "token_count": 200,
    },
    {
        "chunk_id": "seed-chunk-008",
        "doc_id": "seed-doc-001",
        "chunk_index": 8,
        "chunk_text": (
            "6.2 缺陷检查周期\n"
            "水工建筑物缺陷检查分为日常检查、年度详查和特殊检查三类："
            "日常检查每月不少于1次，由运行管理人员执行，主要检查可见裂缝、"
            "渗漏、变形等宏观缺陷，填写日常巡检记录表；年度详查每年进行1次，"
            "应在汛前完成，由专业技术人员执行，包括混凝土强度、碳化深度、"
            "钢筋锈蚀电位等专项检测，提交年度缺陷评估报告；"
            "特殊检查在遭遇设计洪水、地震（震级≥5级）、台风等极端工况后"
            "或发现异常变形和渗漏时立即进行，检查范围应覆盖所有受影响区域。"
            "检查结果应及时录入缺陷管理信息系统，建立缺陷跟踪台账。"
        ),
        "page_number": 52,
        "section_title": "缺陷检查周期",
        "section_number": "6.2",
        "char_start": 12500,
        "char_end": 12900,
        "token_count": 210,
    },
    {
        "chunk_id": "seed-chunk-009",
        "doc_id": "seed-doc-001",
        "chunk_index": 9,
        "chunk_text": (
            "7.1 安全监测要求\n"
            "水工建筑物应设置永久安全监测系统，监测项目至少包括：变形监测"
            "（水平位移、垂直位移、挠度）、渗流监测（渗流量、渗压、绕坝渗流）、"
            "应力应变监测（混凝土应力、钢筋应力、温度）和环境量监测"
            "（水位、水温、气温、降雨量）。混凝土坝变形监测应采用垂线法或"
            "引张线法，水平位移测量精度不低于±1mm；渗流量监测应采用量水堰法，"
            "测量精度不低于±0.1L/s。监测数据应实现自动化采集，采集频率"
            "正常情况下不少于每天1次，汛期加密至每小时1次。监测数据异常时"
            "应自动报警，报警阈值根据历史统计值设定，一般取均值±3倍标准差。"
        ),
        "page_number": 58,
        "section_title": "安全监测要求",
        "section_number": "7.1",
        "char_start": 13800,
        "char_end": 14200,
        "token_count": 230,
    },
    {
        "chunk_id": "seed-chunk-010",
        "doc_id": "seed-doc-001",
        "chunk_index": 10,
        "chunk_text": (
            "8.3 缺陷档案管理\n"
            "每项缺陷应建立独立的缺陷档案，档案内容包括：缺陷编号、发现日期、"
            "缺陷类型与等级、位置描述（含桩号和标高）、检测数据与影像资料、"
            "原因分析报告、处理方案与施工记录、验收报告、后续监测数据。"
            "缺陷档案实行全生命周期管理，从发现、处理到后续跟踪的完整记录"
            "应长期保存。缺陷信息管理系统应具备统计分析功能，可按缺陷类型、"
            "建筑物部位、时间区间等维度生成统计报表和分析图表。"
            "年度缺陷统计分析报告应于次年1月31日前编制完成，"
            "内容包括缺陷变化趋势、处理效果评价及下年度检查重点建议。"
        ),
        "page_number": 65,
        "section_title": "缺陷档案管理",
        "section_number": "8.3",
        "char_start": 15600,
        "char_end": 16000,
        "token_count": 200,
    },
    # ---- seed-doc-002: DLT 2700-2023 (5 chunks) ----
    {
        "chunk_id": "seed-chunk-011",
        "doc_id": "seed-doc-002",
        "chunk_index": 1,
        "chunk_text": (
            "4.1 泄水建筑物安全评价总则\n"
            "泄水建筑物水力安全评价应包括泄洪能力复核、消能防冲设施评价、"
            "空蚀与磨蚀评价、泄水建筑物结构安全评价四个方面的内容。"
            "评价应依据最新水文资料和设计标准进行，当流域水文条件发生显著变化"
            "或泄水建筑物运行超过30年时，应重新进行泄洪能力复核。"
            "安全评价结论分为安全、基本安全和不安全三个等级，"
            "对于评价为不安全或基本安全的泄水建筑物，应提出限制运行条件"
            "或除险加固措施建议。"
        ),
        "page_number": 10,
        "section_title": "泄水建筑物安全评价总则",
        "section_number": "4.1",
        "char_start": 2400,
        "char_end": 2700,
        "token_count": 180,
    },
    {
        "chunk_id": "seed-chunk-012",
        "doc_id": "seed-doc-002",
        "chunk_index": 2,
        "chunk_text": (
            "4.2 泄洪能力复核方法\n"
            "泄洪能力复核应按以下步骤进行："
            "第一步，收集最新水文资料，包括设计洪水、校核洪水、洪水过程线；"
            "第二步，复核泄水建筑物过流能力，包括堰流、孔流和隧洞泄流能力计算；"
            "第三步，进行调洪演算，确定在设计洪水和校核洪水条件下的最高库水位；"
            "第四步，将复核结果与水库原设计洪水标准、现行规范要求进行对比。"
            "泄洪能力不足时，可采取加大泄洪断面、增设泄洪设施或降低正常蓄水位"
            "等措施。复核计算应计入泥沙淤积对库容和泄流能力的影响。"
        ),
        "page_number": 12,
        "section_title": "泄洪能力复核方法",
        "section_number": "4.2",
        "char_start": 2700,
        "char_end": 3100,
        "token_count": 200,
    },
    {
        "chunk_id": "seed-chunk-013",
        "doc_id": "seed-doc-002",
        "chunk_index": 3,
        "chunk_text": (
            "5.1 消能设施安全评价\n"
            "消能设施包括底流消能工、挑流消能工、面流消能工和戽流消能工。"
            "消能设施安全评价应检查以下内容：消力池底板和侧墙的冲刷磨损情况，"
            "消力墩和尾坎的完整性，挑流鼻坎的汽蚀破坏程度，冲刷坑的深度和"
            "发展趋势。当消力池底板冲刷破坏面积超过总面积的30%或局部冲刷深度"
            "超过设计值50%时，应评定为不安全，需进行修复加固。"
            "挑流消能工的冲刷坑后坡比不应陡于1:3，当冲刷坑可能危及坝趾或"
            "两岸边坡稳定时，应采取护岸或预挖冲刷坑等防护措施。"
        ),
        "page_number": 20,
        "section_title": "消能设施安全评价",
        "section_number": "5.1",
        "char_start": 4800,
        "char_end": 5200,
        "token_count": 210,
    },
    {
        "chunk_id": "seed-chunk-014",
        "doc_id": "seed-doc-002",
        "chunk_index": 4,
        "chunk_text": (
            "6.1 冲刷与淘刷评价标准\n"
            "泄水建筑物下游河床和岸坡的冲刷与淘刷评价应包括冲刷坑形态测量、"
            "冲刷深度预测和岸坡稳定性分析。冲刷坑深度超过设计允许值的80%时，"
            "应评定为不安全状态，需采取消能防冲加固措施。岩基河床的允许冲刷深度"
            "应通过地质勘察和水工模型试验确定；软基河床的允许冲刷深度可取"
            "护坦末端基础埋深的1.5倍。对于已发生严重淘刷的岸坡，"
            "可采用抛石护脚、钢筋混凝土护坡或抗滑桩等措施进行加固。"
            "冲刷监测应每年在汛后进行一次水下地形测量，测量范围应覆盖"
            "泄水建筑物下游不小于500m的河段。"
        ),
        "page_number": 28,
        "section_title": "冲刷与淘刷评价标准",
        "section_number": "6.1",
        "char_start": 6800,
        "char_end": 7200,
        "token_count": 200,
    },
    {
        "chunk_id": "seed-chunk-015",
        "doc_id": "seed-doc-002",
        "chunk_index": 5,
        "chunk_text": (
            "7.3 泄水建筑物维护要求\n"
            "泄水建筑物应建立定期维护制度：每年汛前应完成泄水建筑物全面检查和"
            "维护，包括清除进水口拦污栅前的漂浮物、疏通排水系统、修复混凝土"
            "表面破损和裂缝；汛后应进行水下检查，重点检查消力池底板、护坦和"
            "挑流鼻坎等水下部分的冲刷破坏情况。混凝土表面剥蚀深度超过5mm或"
            "面积超过0.5m²时应及时修补，修补材料应与原混凝土的强度和耐久性"
            "相匹配，优先选用聚合物改性砂浆或环氧砂浆。止水结构损坏导致渗漏时，"
            "应在枯水期进行修复，修复后应进行压水试验验证止水效果。"
            "泄水建筑物累计运行时间超过5000小时或泄洪次数超过50次时，"
            "应进行一次全面的安全检测评估。"
        ),
        "page_number": 35,
        "section_title": "泄水建筑物维护要求",
        "section_number": "7.3",
        "char_start": 8400,
        "char_end": 8800,
        "token_count": 230,
    },
]


def create_schema(conn) -> None:
    """按 ICD-01 §4 在 PostgreSQL 创建 metadata schema 和三张表。

    幂等：表已存在则跳过。
    """
    cur = conn.cursor()

    cur.execute("CREATE SCHEMA IF NOT EXISTS metadata")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # §4.1 原始文档元数据
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metadata.documents (
            doc_id           VARCHAR(64) PRIMARY KEY,
            doc_type         VARCHAR(32)  NOT NULL,
            title            VARCHAR(512) NOT NULL,
            authors          TEXT[],
            source_org       VARCHAR(256),
            publish_date     DATE,
            version          VARCHAR(32),
            language         VARCHAR(16)  DEFAULT 'zh-CN',
            file_format      VARCHAR(16)  NOT NULL,
            file_path        VARCHAR(1024) NOT NULL,
            file_size_bytes  BIGINT,
            permission_level VARCHAR(16)  DEFAULT 'internal',
            tags             TEXT[],
            abstract         TEXT,
            uploaded_at      TIMESTAMPTZ  DEFAULT NOW(),
            updated_at       TIMESTAMPTZ  DEFAULT NOW()
        )
    """)

    # §4.3 Chunk 元数据
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metadata.chunks (
            chunk_id         VARCHAR(64) PRIMARY KEY,
            doc_id           VARCHAR(64) NOT NULL REFERENCES metadata.documents(doc_id),
            chunk_index      INTEGER NOT NULL,
            chunk_text       TEXT NOT NULL,
            page_number      INTEGER,
            section_title    VARCHAR(256),
            section_number   VARCHAR(32),
            char_start       INTEGER,
            char_end         INTEGER,
            token_count      INTEGER,
            parent_chunk_id  VARCHAR(64),
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
        ON metadata.chunks(doc_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_section
        ON metadata.chunks(doc_id, section_number)
    """)

    # §4.4 Embedding 向量元数据
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metadata.embeddings (
            embedding_id      VARCHAR(64) PRIMARY KEY,
            chunk_id          VARCHAR(64) NOT NULL REFERENCES metadata.chunks(chunk_id),
            embedding_model   VARCHAR(64) NOT NULL,
            vector_dimension  INTEGER NOT NULL,
            milvus_id         BIGINT NOT NULL,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_chunk_id
        ON metadata.embeddings(chunk_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_milvus_id
        ON metadata.embeddings(milvus_id)
    """)


def insert_documents(conn) -> list[dict]:
    """插入种子文档到 metadata.documents。幂等：已存在则跳过。"""
    cur = conn.cursor()
    for doc in SEED_DOCUMENTS:
        cur.execute(
            "INSERT INTO metadata.documents "
            "(doc_id, doc_type, title, authors, source_org, publish_date, "
            "version, language, file_format, file_path, file_size_bytes, "
            "permission_level, tags, abstract) "
            "VALUES (%(doc_id)s, %(doc_type)s, %(title)s, %(authors)s, "
            "%(source_org)s, %(publish_date)s, %(version)s, %(language)s, "
            "%(file_format)s, %(file_path)s, %(file_size_bytes)s, "
            "%(permission_level)s, %(tags)s, %(abstract)s) "
            "ON CONFLICT (doc_id) DO NOTHING",
            doc,
        )
    return SEED_DOCUMENTS


def insert_chunks(conn) -> list[dict]:
    """插入种子 chunk 到 metadata.chunks。幂等：已存在则跳过。"""
    cur = conn.cursor()
    for chunk in SEED_CHUNKS:
        cur.execute(
            "INSERT INTO metadata.chunks "
            "(chunk_id, doc_id, chunk_index, chunk_text, page_number, "
            "section_title, section_number, char_start, char_end, token_count) "
            "VALUES (%(chunk_id)s, %(doc_id)s, %(chunk_index)s, %(chunk_text)s, "
            "%(page_number)s, %(section_title)s, %(section_number)s, "
            "%(char_start)s, %(char_end)s, %(token_count)s) "
            "ON CONFLICT (chunk_id) DO NOTHING",
            chunk,
        )
    return SEED_CHUNKS


def generate_embeddings(
    chunks: list[dict],
    ollama_url: str = "http://localhost:11435",
    model: str = "bge-m3",
) -> list[list[float]]:
    """通过 Ollama API 为每个 chunk 生成 embedding 向量。

    Returns: list of 1024-d float vectors, 与 chunks 顺序一致。
    """
    import httpx

    vectors = []
    for chunk in chunks:
        resp = httpx.post(
            f"{ollama_url}/api/embeddings",
            json={"model": model, "prompt": chunk["chunk_text"]},
            timeout=30,
        )
        resp.raise_for_status()
        embedding = resp.json()["embedding"]
        vectors.append(embedding)
    return vectors


def create_milvus_collection(client, collection_name: str = "seed_chunks") -> None:
    """在 Milvus 创建集合，按 ICD-01 §6 定义 Schema。

    字段: id(int64 PK) + chunk_id(VarChar) + doc_id(VarChar) + vector(1024-dim)
    索引在 insert_embeddings_to_milvus 中插入数据后构建（IVF_FLAT 需要训练数据）。
    幂等：集合已存在则跳过。
    """
    from pymilvus import DataType

    if client.has_collection(collection_name):
        return

    schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)

    client.create_collection(collection_name=collection_name, schema=schema)


def insert_embeddings_to_milvus(
    client,
    chunks: list[dict],
    vectors: list[list[float]],
    collection_name: str = "seed_chunks",
) -> dict:
    """将 embedding 向量插入 Milvus 集合，并构建 IVF_FLAT 索引。

    幂等：若 collection 已有数据，跳过插入。

    Returns: {"insert_count": N, "ids": [id1, id2, ...], "skipped": bool}
    """
    # 检查是否已有数据（比 get_collection_stats 更可靠）
    try:
        client.load_collection(collection_name)
        existing = client.query(
            collection_name, filter="id >= 0", output_fields=["id"], limit=1
        )
        if existing:
            return {"insert_count": 0, "ids": [], "skipped": True}
    except Exception:
        pass  # 索引未构建或加载失败，继续插入

    data = [
        {"vector": vec, "chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"]}
        for chunk, vec in zip(chunks, vectors)
    ]
    result = client.insert(
        collection_name=collection_name,
        data=data,
    )

    # 插入数据后构建 IVF_FLAT 索引（ICD-01 §6.2，nlist 自适应数据量）
    nlist = min(1024, max(1, len(chunks) // 2))
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": nlist},
    )
    client.create_index(collection_name=collection_name, index_params=index_params)

    return {
        "insert_count": result["insert_count"],
        "ids": result["ids"],
        "skipped": False,
    }


def insert_embeddings_metadata(
    conn,
    chunks: list[dict],
    milvus_ids: list[int],
    model: str = "bge-m3",
    dimension: int = 1024,
) -> list[dict]:
    """将 embedding 元数据写入 PostgreSQL metadata.embeddings。

    embedding_id 格式: seed-emb-{序号}。幂等：chunk_id 已存在则跳过。
    """
    cur = conn.cursor()
    records = []
    for i, (chunk, milvus_id) in enumerate(zip(chunks, milvus_ids), start=1):
        embedding_id = f"seed-emb-{i:03d}"
        cur.execute(
            "INSERT INTO metadata.embeddings "
            "(embedding_id, chunk_id, embedding_model, vector_dimension, milvus_id) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (chunk_id) DO NOTHING",
            (embedding_id, chunk["chunk_id"], model, dimension, milvus_id),
        )
        records.append(
            {
                "embedding_id": embedding_id,
                "chunk_id": chunk["chunk_id"],
                "embedding_model": model,
                "vector_dimension": dimension,
                "milvus_id": milvus_id,
            }
        )
    return records


def retrieve_similar_chunks(
    query_text: str,
    ollama_url: str,
    milvus_client,
    db_conn,
    top_k: int = 3,
    model: str = "bge-m3",
    collection_name: str = "seed_chunks",
) -> list[dict]:
    """端到端检索：query → embed → Milvus search → PostgreSQL lookup。

    Returns: [{"chunk_id", "chunk_text", "doc_id", "title", "score"}, ...]
    """
    import httpx

    # 1. Embed query
    resp = httpx.post(
        f"{ollama_url}/api/embeddings",
        json={"model": model, "prompt": query_text},
        timeout=30,
    )
    resp.raise_for_status()
    query_vector = resp.json()["embedding"]

    # 2. Search Milvus
    milvus_client.load_collection(collection_name)
    search_results = milvus_client.search(
        collection_name=collection_name,
        data=[query_vector],
        limit=top_k,
        output_fields=["chunk_id", "doc_id"],
    )

    # 3. Look up chunk + document metadata in PostgreSQL
    cur = db_conn.cursor()
    results = []
    seen = set()
    for hit in search_results[0]:
        entity = hit.get("entity", {})
        milvus_chunk_id = entity.get("chunk_id", "")
        if not milvus_chunk_id:
            continue
        if milvus_chunk_id in seen:
            continue
        seen.add(milvus_chunk_id)

        cur.execute(
            "SELECT c.chunk_id, c.chunk_text, c.doc_id, d.title "
            "FROM metadata.chunks c "
            "JOIN metadata.documents d ON c.doc_id = d.doc_id "
            "WHERE c.chunk_id = %s",
            (milvus_chunk_id,),
        )
        row = cur.fetchone()
        if row:
            results.append(
                {
                    "chunk_id": row[0],
                    "chunk_text": row[1],
                    "doc_id": row[2],
                    "title": row[3],
                    "score": hit["distance"],
                }
            )

    return results


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys

    import psycopg2
    from pymilvus import MilvusClient

    refresh = "--refresh" in sys.argv

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        host="localhost",
        port=5434,
        user="daduhe",
        password="gis31415",
        dbname="mydatabase",
    )
    conn.autocommit = True

    print("Connecting to Milvus...")
    milvus_client = MilvusClient(
        uri="http://10.222.124.211:19530",
        user="daduhe",
        password="gis31415",
        db_name="daduhe_milvus_database",
    )

    # === PostgreSQL (幂等: ON CONFLICT DO NOTHING) ===
    print("Creating schema...")
    create_schema(conn)
    print("Inserting documents...")
    insert_documents(conn)
    print("Inserting chunks...")
    insert_chunks(conn)

    # === Milvus ===
    if refresh:
        if milvus_client.has_collection("seed_chunks"):
            milvus_client.drop_collection("seed_chunks")
            print("Dropped existing seed_chunks collection for refresh.")

    create_milvus_collection(milvus_client)

    print("Generating embeddings via Ollama (bge-m3)...")
    vectors = generate_embeddings(SEED_CHUNKS)

    print("Inserting vectors into Milvus...")
    result = insert_embeddings_to_milvus(milvus_client, SEED_CHUNKS, vectors)

    if result["skipped"]:
        print("  Milvus already has seed data — skipped.")
    else:
        print(f"  Inserted {result['insert_count']} vectors.")

    print("Writing embedding metadata to PostgreSQL...")
    records = insert_embeddings_metadata(conn, SEED_CHUNKS, result["ids"])
    if result["skipped"]:
        print("  PostgreSQL embeddings already exist — skipped.")
    else:
        print(f"  Written {len(records)} records.")

    conn.close()

    print()
    print("Done.")
    print(
        f"  PostgreSQL: {len(SEED_DOCUMENTS)} documents, {len(SEED_CHUNKS)} chunks, {len(SEED_CHUNKS)} embeddings"
    )
    print(f"  Milvus:     seed_chunks collection ({len(SEED_CHUNKS)} vectors)")
    print()
    print("Run tests:  uv run pytest tests/test_seed.py -v")
    print("Verify:     uv run python scripts/seed_data.py --verify  (coming soon)")
