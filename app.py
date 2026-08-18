import io
import re
import pandas as pd
import pdfplumber
import streamlit as st

# --- 画面初期設定 ---
st.set_page_config(
    page_title="SDS GHS判定＆対策出力ツール（日英対応版）",
    layout="wide",
)

# --- パスワード認証機能 ---
PASSWORD = "ウチクラユウキ"

def check_password():
    """パスワード認証を行い、成功すれば True、未認証なら False を返す"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔒 ログイン")
        st.write("アプリを利用するにはパスワードの入力が必要です。")
        
        input_password = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン", type="primary"):
            if input_password == PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("パスワードが間違っています。")
        return False
    return True


# パスワード認証が完了した場合のみメイン処理を実行
if check_password():

    st.title("🧪 SDS GHS有害性ランクを石野貴史と南悟大が判定します！")
    st.caption(
        "【完全ローカル版】日本語・英語のSDS（PDF）を自動解析し、管理ランクと現場対策を出力します。"
    )

    # --- GHSランク判定マスタ（貴社基準） ---
    RANK_MASTER = {
        "S": {
            "label": "ランクS（極めて危険）",
            "color": "#ff4b4b",
            "equipment": "完全密閉 または 局所排気装置の必須設置（暴露防止）",
            "ppe_hands": "耐薬品・不浸透性手袋（ニトリル手袋等。※軍手NG）",
            "ppe_eyes": "保護ゴーグル / 防災面",
            "ppe_respirator": "有機ガス用防毒マスク または 国家検定合格品防塵マスク(DS2等)",
            "rules": "作業記録の長期保存（最大30年）、鍵付き厳重保管、作業前の手順確認徹底",
        },
        "A": {
            "label": "ランクA（高い危険性）",
            "color": "#ffa500",
            "equipment": "局所排気装置 または 強制換気設備の設置（静電気アース対策）",
            "ppe_hands": "不浸透性手袋（ニトリル手袋等。※軍手NG）",
            "ppe_eyes": "保護メガネ（ゴーグル型推奨）",
            "ppe_respirator": "防毒マスク または 防塵マスク(DS2等)",
            "rules": "直接（素手）接触の禁止、汚染衣類の持ち出し禁止・即時洗濯、作業後の手洗い・うがい徹底",
        },
        "B": {
            "label": "ランクB（中程度）",
            "color": "#1e90ff",
            "equipment": "全体換気設備（定期的な空気の入れ替え）",
            "ppe_hands": "不浸透性手袋（作業用ゴム手袋等）",
            "ppe_eyes": "保護メガネ",
            "ppe_respirator": "一般的な防塵マスク（粉体取り扱い時）",
            "rules": "取扱エリアでの飲食・喫煙の絶対禁止、手洗いの徹底（手口経由の誤飲防止）",
        },
        "C": {
            "label": "ランクC（低危険性）",
            "color": "#2ed573",
            "equipment": "基本的な室内換気（※パウダー品は静電気対策・爆発警戒）",
            "ppe_hands": "必要に応じて作業手袋（手荒れ防止）",
            "ppe_eyes": "必要に応じて保護メガネ",
            "ppe_respirator": "必要に応じて防塵マスク（粉舞い時）",
            "rules": "標準的な作業手順の遵守、作業後の手洗い（パウダー品は粉塵の飛散防止）",
        },
    }

    # --- SDS精密解析ロジック（日英対応） ---
    def analyze_sds_pdf(file_stream):
        full_text = ""
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # 最終ページの「略語集」以降をカットして誤検知を防止（日英対応）
                    if "略語および頭字語" in text or "Abbreviations and acronyms" in text:
                        text = re.split(
                            r"略語および頭字語|Abbreviations and acronyms", text
                        )[0]
                    full_text += text + "\n"

        # 全角数字を半角数字に変換
        norm_text = full_text.translate(
            str.maketrans("０１２３４５６７８９", "0123456789")
        )

        # 製品名の抽出（日本語・英語対応）
        product_name = "製品名取得失敗 (Product Name Unknown)"
        name_match = re.search(
            r"(?:製品名|化学品の名?称|Product name|Trade name)[\s:：]+([^\n]+)",
            norm_text,
            re.IGNORECASE,
        )
        if name_match:
            product_name = name_match.group(1).strip()

        detected_reasons = []

        # 否定・無害判定の単語（日本語・英語）が含まれるかチェックする関数
        def is_valid_hazard(pattern):
            matches = re.finditer(pattern, norm_text, re.IGNORECASE)
            for m in matches:
                # 該当箇所の前後を抽出して打ち消し語がないか確認
                start = max(0, m.start() - 10)
                end = min(len(norm_text), m.end() + 40)
                snippet = norm_text[start:end].lower()

                # 否定語（日本語＋英語）
                negatives = [
                    "データなし",
                    "区分外",
                    "分類対象外",
                    "分類できない",
                    "該当しない",
                    "規制されない",
                    "no data",
                    "not classified",
                    "not applicable",
                    "classification not possible",
                    "not regulated",
                ]
                if not any(neg in snippet for neg in negatives):
                    return True
            return False

        # --- ランクSのチェック（日本語・英語） ---
        s_patterns = [
            r"(?:発がん性|Carcinogenicity)[^\n]{0,30}(?:区分1|1A|1B|Category\s*1)",
            r"(?:生殖細胞変異原性|Germ cell mutagenicity)[^\n]{0,30}(?:区分1|1A|1B|Category\s*1)",
            r"(?:生殖毒性|Reproductive toxicity)[^\n]{0,30}(?:区分1|1A|1B|Category\s*1)",
            r"(?:呼吸器感作性|Respiratory sensiti[za]tion)[^\n]{0,30}(?:区分1|Category\s*1)",
        ]
        for p in s_patterns:
            if is_valid_hazard(p):
                detected_reasons.append(
                    "S判定項目（発がん性/変異原性/生殖毒性/感作性 区分1 / Category 1）を検出"
                )

        if detected_reasons:
            rank = "S"
        else:
            # --- ランクAのチェック（日本語・英語） ---
            a_patterns = [
                r"(?:発がん性|Carcinogenicity)[^\n]{0,30}(?:区分2|Category\s*2)",
                r"(?:生殖毒性|Reproductive toxicity)[^\n]{0,30}(?:区分2|Category\s*2)",
                r"(?:皮膚感作性|Skin sensiti[za]tion)[^\n]{0,30}(?:区分1|Category\s*1)",
                r"(?:急性毒性|Acute toxicity)[^\n]{0,30}(?:区分1|区分2|区分3|Category\s*[123])",
            ]
            for p in a_patterns:
                if is_valid_hazard(p):
                    detected_reasons.append(
                        "A判定項目（区分2毒性/皮膚感作性/急性毒性1〜3 / Category 1-3）を検出"
                    )

            if detected_reasons:
                rank = "A"
            else:
                # --- ランクBのチェック（日本語・英語） ---
                b_patterns = [
                    r"(?:急性毒性|Acute toxicity)[^\n]{0,30}(?:区分4|Category\s*4)",
                    r"(?:皮膚腐食性|Skin corrosion)[^\n]{0,30}(?:区分1|区分2|Category\s*[12])",
                    r"(?:皮膚刺激性|Skin irritation)[^\n]{0,30}(?:区分1|区分2|Category\s*[12])",
                    r"(?:眼刺激性|Eye irritation)[^\n]{0,30}(?:区分1|Category\s*[12])",
                ]
                for p in b_patterns:
                    if is_valid_hazard(p):
                        detected_reasons.append(
                            "B判定項目（急性毒性4/皮膚・眼刺激性等 / Category 4）を検出"
                        )

                if detected_reasons:
                    rank = "B"
                else:
                    rank = "C"
                    detected_reasons.append(
                        "該当する危険有害性区分なし（またはすべて区分外・データなし / Not classified）"
                    )

        # パウダー（粉末・ペレット）チェック（日本語・英語対応）
        is_powder = bool(
            re.search(
                r"(粉末|パウダー|粉じん|ペレット|powder|pellet|dust|solid)",
                norm_text,
                re.IGNORECASE,
            )
        )

        return {
            "product_name": product_name,
            "rank": rank,
            "ghs_categories": " / ".join(list(set(detected_reasons))),
            "is_powder": is_powder,
        }

    # --- メイン画面 ---
    uploaded_file = st.file_uploader(
        "SDSのPDFファイルをドラッグ＆ドロップしてください（日本語・英語対応）",
        type=["pdf"],
    )

    if uploaded_file:
        if st.button("🔍 判定を実行する", type="primary"):
            with st.spinner("PDFを解析中..."):
                try:
                    result = analyze_sds_pdf(uploaded_file)
                    rank = result["rank"]
                    rank_info = RANK_MASTER[rank]

                    powder_note = ""
                    if result["is_powder"] and rank == "C":
                        powder_note = "【警戒】形状が粉末・ペレット等のため、粉塵爆発や取り扱い時の飛散にご留意ください。"

                    st.success("解析が完了しました！")

                    # --- 画面表示 ---
                    st.markdown("---")
                    st.subheader("■ 1. 物質の基本情報")
                    st.write(f"**・製品名：** {result['product_name']}")

                    st.subheader("■ 2. テラボウの管理ランク判定")
                    st.markdown(
                        f"<h2 style='color: {rank_info['color']};'>{rank_info['label']}</h2>",
                        unsafe_allow_html=True,
                    )
                    st.write(f"**・判定根拠：** {result['ghs_categories']}")
                    if powder_note:
                        st.warning(powder_note)

                    st.subheader("■ 3. 現場の「安全基準・現場対策」")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**【設備・環境対策】**")
                        st.write(f"・{rank_info['equipment']}")
                        st.markdown("**【実務上の義務・注意点】**")
                        st.write(f"・{rank_info['rules']}")

                    with col2:
                        st.markdown("**【必須保護具（PPE）】**")
                        st.write(f"・手：{rank_info['ppe_hands']}")
                        st.write(f"・目：{rank_info['ppe_eyes']}")
                        st.write(f"・呼吸器：{rank_info['ppe_respirator']}")

                    # --- Excelデータ出力 ---
                    excel_data = {
                        "項目": [
                            "製品名",
                            "判定ランク",
                            "判定根拠",
                            "設備・環境対策",
                            "保護具（手）",
                            "保護具（目）",
                            "保護具（呼吸器）",
                            "実務上の義務・注意点",
                        ],
                        "内容": [
                            result["product_name"],
                            rank_info["label"],
                            result["ghs_categories"]
                            + (f"\n{powder_note}" if powder_note else ""),
                            rank_info["equipment"],
                            rank_info["ppe_hands"],
                            rank_info["ppe_eyes"],
                            rank_info["ppe_respirator"],
                            rank_info["rules"],
                        ],
                    }

                    df = pd.DataFrame(excel_data)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="GHS判定シート")
                    processed_data = output.getvalue()

                    st.markdown("---")
                    st.download_button(
                        label="📥 判定結果をExcelファイルでダウンロード",
                        data=processed_data,
                        file_name=f"GHS判定_{result['product_name']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                    )

                except Exception as e:
                    st.error(f"解析中にエラーが発生しました: {e}")
