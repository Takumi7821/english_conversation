import streamlit as st
import os
import time
from time import sleep
from pathlib import Path
from streamlit.components.v1 import html
from langchain.memory import ConversationSummaryBufferMemory
from langchain.chains import ConversationChain
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain.schema import SystemMessage
from openai import OpenAI
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import functions as ft
import constants as ct
import json


# 各種設定
load_dotenv()
st.set_page_config(
    page_title=ct.APP_NAME
)

# タイトル表示
st.markdown(f"## {ct.APP_NAME}")

# サイドバーメニュー（ホーム/練習/履歴/設定/ヘルプ）と精度モード
menu = st.sidebar.selectbox("メニュー", ["ホーム", "練習", "履歴", "設定", "ヘルプ"], index=0)
precision_mode = st.sidebar.checkbox("精度優先モード", value=False, key="precision_mode")

# メニュー切替で自動的に発話開始しないようにする（"練習"へ切替時は開始フラグをリセット）
if "prev_menu" not in st.session_state:
    st.session_state.prev_menu = None
if menu == "練習" and st.session_state.prev_menu != "練習":
    st.session_state.start_flg = False
st.session_state.prev_menu = menu

# ボタンの視認性を上げるための簡易スタイル（プライマリボタンを黒背景/白文字に）
st.markdown(
    """
    <style>
    /* Streamlit のボタン要素に対する簡易スタイル */
    .stButton>button,
    .stDownloadButton>button,
    button,
    input[type="button"] {
        background-color: #000000 !important;
        color: #ffffff !important;
        border: none !important;
        padding: 0.5rem 0.75rem !important;
        border-radius: 6px !important;
        transition: none !important;
        -webkit-appearance: none !important;
        appearance: none !important;
        background-image: none !important;
        opacity: 1 !important;
    }
    /* Hover / Focus / Active / Visited でも反転・影・フィルタを無効化 */
    .stButton>button:hover,
    .stDownloadButton>button:hover,
    button:hover,
    input[type="button"]:hover,
    .stButton>button:focus,
    .stDownloadButton>button:focus,
    button:focus,
    input[type="button"]:focus,
    .stButton>button:active,
    .stDownloadButton>button:active,
    button:active,
    input[type="button"]:active,
    a:visited {
        background-color: #000000 !important;
        color: #ffffff !important;
        box-shadow: none !important;
        outline: none !important;
        -webkit-filter: none !important;
        filter: none !important;
        background-image: none !important;
        opacity: 1 !important;
        transition: none !important;
    }
    /* インラインスタイルで与えられる場合の上書き保険 */
    .stButton>button[style], button[style] {
        background-color: #000000 !important;
        color: #ffffff !important;
        opacity: 1 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# メニューページ表示（練習以外はここで処理して終了）
if menu != "練習":
    if menu == "ホーム":
        st.header("ようこそ")
        st.write("音声で練習できる英会話アプリです。左のメニューで『練習』を選んで開始してください。")
    elif menu == "履歴":
        st.header("練習履歴")
        for m in st.session_state.get("messages", []):
            role = m.get("role")
            content = m.get("content")
            st.markdown(f"**{role}**: {content}")
    elif menu == "設定":
        st.header("設定")
        # 精度優先モードはサイドバーのトグルで制御するため、ここでは状態表示のみ行う
        current = st.session_state.get("precision_mode", False)
        st.write(f"精度優先モード: {'ON' if current else 'OFF'}")
        st.info("精度優先モードはサイドバーのチェックボックスで切り替えてください。")
        if st.button("履歴をクリア"):
            st.session_state.messages = []
            st.success("履歴をクリアしました")
    elif menu == "ヘルプ":
        st.header("ヘルプ")
        st.write("モードを選んで『開始』を押すと、それぞれの練習が始まります。日常英会話では活動タイプを選べます。")
    st.stop()


# 初期処理
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.start_flg = False
    st.session_state.pre_mode = ""
    st.session_state.shadowing_flg = False
    st.session_state.shadowing_button_flg = False
    st.session_state.shadowing_count = 0
    st.session_state.shadowing_first_flg = True
    st.session_state.shadowing_audio_input_flg = False
    st.session_state.shadowing_evaluation_first_flg = True
    st.session_state.dictation_flg = False
    st.session_state.dictation_button_flg = False
    st.session_state.dictation_count = 0
    st.session_state.dictation_first_flg = True
    st.session_state.dictation_chat_message = ""
    st.session_state.dictation_evaluation_first_flg = True
    st.session_state.chat_open_flg = False
    st.session_state.problem = ""
    
    st.session_state.openai_obj = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    # 精度優先モードでは温度を下げる（実際のウィジェット状態を優先して参照）
    temp = 0.2 if st.session_state.get("precision_mode", False) else 0.5
    st.session_state.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=temp)
    st.session_state.memory = ConversationSummaryBufferMemory(
        llm=st.session_state.llm,
        max_token_limit=1000,
        return_messages=True
    )
    # モード「日常英会話」用のChain作成
    if st.session_state.get("precision_mode", False):
        system_template = ct.SYSTEM_TEMPLATE_STRICT_RESPONSE + "\n\n" + ct.SYSTEM_TEMPLATE_BASIC_CONVERSATION
    else:
        system_template = ct.SYSTEM_TEMPLATE_BASIC_CONVERSATION
    st.session_state.chain_basic_conversation = ft.create_chain(system_template)
    # 応答検証チェーンも作成
    st.session_state.chain_response_verifier = ft.create_chain(ct.SYSTEM_TEMPLATE_RESPONSE_VERIFICATION)

# 初期表示
# col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
# 提出課題用
col1, col2, col3, col4 = st.columns([2, 2, 3, 3])
with col1:
    if st.session_state.start_flg:
        st.button("開始", use_container_width=True, type="primary")
    else:
        st.session_state.start_flg = st.button("開始", use_container_width=True, type="primary")
with col2:
    st.session_state.speed = st.selectbox(label="再生速度", options=ct.PLAY_SPEED_OPTION, index=3, label_visibility="collapsed")
with col3:
    st.session_state.mode = st.selectbox(label="モード", options=[ct.MODE_1, ct.MODE_2, ct.MODE_3], label_visibility="collapsed")
    # モードを変更した際の処理
    if st.session_state.mode != st.session_state.pre_mode:
        # 自動でそのモードの処理が実行されないようにする
        st.session_state.start_flg = False
        # 「日常英会話」選択時の初期化処理
        if st.session_state.mode == ct.MODE_1:
            st.session_state.dictation_flg = False
            st.session_state.shadowing_flg = False
        # 「シャドーイング」選択時の初期化処理
        st.session_state.shadowing_count = 0
        if st.session_state.mode == ct.MODE_2:
            st.session_state.dictation_flg = False
        # 「ディクテーション」選択時の初期化処理
        st.session_state.dictation_count = 0
        if st.session_state.mode == ct.MODE_3:
            st.session_state.shadowing_flg = False
        # チャット入力欄を非表示にする
        st.session_state.chat_open_flg = False
    st.session_state.pre_mode = st.session_state.mode
with col4:
    st.session_state.englv = st.selectbox(label="英語レベル", options=ct.ENGLISH_LEVEL_OPTION, label_visibility="collapsed")
# 練習タイプ（日本語）を常時表示して選べるようにする
jp_options = ["自由会話", "ロールプレイ", "フレーズ練習", "スモールトーク", "発音アドバイス", "練習プラン"]
en_to_jp = {
    "Free Conversation": "自由会話",
    "Roleplay": "ロールプレイ",
    "Phrase Drill": "フレーズ練習",
    "Small Talk": "スモールトーク",
    "Pronunciation Tip": "発音アドバイス",
    "Practice Goal": "練習プラン",
}
jp_to_en = {v: k for k, v in en_to_jp.items()}
current_activity = st.session_state.get("activity", "自由会話")
if current_activity in en_to_jp:
    current_display = en_to_jp[current_activity]
else:
    current_display = current_activity
try:
    current_index = jp_options.index(current_display)
except ValueError:
    current_index = 0
new_activity = st.selectbox("練習タイプ", jp_options, index=current_index)
# 練習タイプを切り替えたら履歴をクリア
if new_activity != current_display:
    st.session_state.messages = []
st.session_state.activity = new_activity

# シャドーイング／ディクテーションの簡易タイプ選択
if "shadowing_activity" not in st.session_state:
    st.session_state.shadowing_activity = "通常"
if "dictation_activity" not in st.session_state:
    st.session_state.dictation_activity = "通常"
if st.session_state.mode == ct.MODE_2:
    st.session_state.shadowing_activity = st.selectbox("シャドーイングタイプ", ["通常", "長めの文", "速度変更"], index=["通常", "長めの文", "速度変更"].index(st.session_state.shadowing_activity))
if st.session_state.mode == ct.MODE_3:
    st.session_state.dictation_activity = st.selectbox("ディクテーションタイプ", ["通常", "スローモード", "分割再生"], index=["通常", "スローモード", "分割再生"].index(st.session_state.dictation_activity))
with st.chat_message("assistant", avatar="images/ai_icon.jpg"):
    st.markdown("こちらは生成AIによる音声英会話の練習アプリです。何度も繰り返し練習し、英語力をアップさせましょう。")
    st.markdown("**【操作説明】**")
    st.success("""
    - モードと再生速度を選択し、「英会話開始」ボタンを押して英会話を始めましょう。
    - モードは「日常英会話」「シャドーイング」「ディクテーション」から選べます。
    - 発話後、5秒間沈黙することで音声入力が完了します。
    - 「一時中断」ボタンを押すことで、英会話を一時中断できます。
    """)
st.divider()

# メッセージリストの一覧表示
for message in st.session_state.messages:
    if message["role"] == "assistant":
        with st.chat_message(message["role"], avatar="images/ai_icon.jpg"):
            st.markdown(message["content"])
    elif message["role"] == "user":
        with st.chat_message(message["role"], avatar="images/user_icon.jpg"):
            st.markdown(message["content"])
    else:
        st.divider()

# LLMレスポンスの下部にモード実行のボタン表示
if st.session_state.shadowing_flg:
    st.session_state.shadowing_button_flg = st.button("シャドーイング開始", type="primary")
if st.session_state.dictation_flg:
    st.session_state.dictation_button_flg = st.button("ディクテーション開始", type="primary")

# 「ディクテーション」モードのチャット入力受付時に実行
if st.session_state.chat_open_flg:
    st.info("AIが読み上げた音声を、画面下部のチャット欄からそのまま入力・送信してください。")

st.session_state.dictation_chat_message = st.chat_input("※「ディクテーション」選択時以外は送信不可")

if st.session_state.dictation_chat_message and not st.session_state.chat_open_flg:
    st.stop()

# 「英会話開始」ボタンが押された場合の処理
if st.session_state.start_flg:

    # モード：「ディクテーション」
    # 「ディクテーション」ボタン押下時か、「英会話開始」ボタン押下時か、チャット送信時
    if st.session_state.mode == ct.MODE_3 and (st.session_state.dictation_button_flg or st.session_state.dictation_count == 0 or st.session_state.dictation_chat_message):
        if st.session_state.dictation_first_flg:
            st.session_state.chain_create_problem = ft.create_chain(ct.SYSTEM_TEMPLATE_CREATE_PROBLEM)
            st.session_state.dictation_first_flg = False
        # チャット入力以外
        if not st.session_state.chat_open_flg:
            with st.spinner('問題文生成中...'):
                st.session_state.problem, llm_response_audio = ft.create_problem_and_play_audio()

            st.session_state.chat_open_flg = True
            st.session_state.dictation_flg = False
            st.rerun()
        # チャット入力時の処理
        else:
            # チャット欄から入力された場合にのみ評価処理が実行されるようにする
            if not st.session_state.dictation_chat_message:
                st.stop()
            
            # AIメッセージとユーザーメッセージの画面表示
            with st.chat_message("assistant", avatar=ct.AI_ICON_PATH):
                st.markdown(st.session_state.problem)
            with st.chat_message("user", avatar=ct.USER_ICON_PATH):
                st.markdown(st.session_state.dictation_chat_message)

            # LLMが生成した問題文とチャット入力値をメッセージリストに追加
            st.session_state.messages.append({"role": "assistant", "content": st.session_state.problem})
            st.session_state.messages.append({"role": "user", "content": st.session_state.dictation_chat_message})
            
            with st.spinner('評価結果の生成中...'):
                system_template = ct.SYSTEM_TEMPLATE_EVALUATION.format(
                    llm_text=st.session_state.problem,
                    user_text=st.session_state.dictation_chat_message
                )
                st.session_state.chain_evaluation = ft.create_chain(system_template)
                # 問題文と回答を比較し、評価結果の生成を指示するプロンプトを作成
                llm_response_evaluation = ft.create_evaluation()
            
            # 評価結果のメッセージリストへの追加と表示
            with st.chat_message("assistant", avatar=ct.AI_ICON_PATH):
                st.markdown(llm_response_evaluation)
            st.session_state.messages.append({"role": "assistant", "content": llm_response_evaluation})
            st.session_state.messages.append({"role": "other"})
            
            # 各種フラグの更新
            st.session_state.dictation_flg = True
            st.session_state.dictation_chat_message = ""
            st.session_state.dictation_count += 1
            st.session_state.chat_open_flg = False

            st.rerun()

    
    # モード：「日常英会話」
    if st.session_state.mode == ct.MODE_1:
        activity_en = jp_to_en.get(st.session_state.activity, "Free Conversation")

        if activity_en == "Free Conversation":
            # 音声入力フロー（従来の会話）
            audio_input_file_path = f"{ct.AUDIO_INPUT_DIR}/audio_input_{int(time.time())}.wav"
            ft.record_audio(audio_input_file_path)

            with st.spinner('音声入力をテキストに変換中...'):
                transcript = ft.transcribe_audio(audio_input_file_path)
                audio_input_text = transcript.text

            with st.chat_message("user", avatar=ct.USER_ICON_PATH):
                st.markdown(audio_input_text)

            with st.spinner("回答の音声読み上げ準備中..."):
                # ユーザー入力値をLLMに渡して回答取得
                llm_response = st.session_state.chain_basic_conversation.predict(input=audio_input_text)

                # 応答検証を行い、低信頼なら精度優先で再生成
                try:
                    verifier_input = f"USER_INPUT:\n{audio_input_text}\nMODEL_ANSWER:\n{llm_response}"
                    verification_result = st.session_state.chain_response_verifier.predict(input=verifier_input)
                    parsed = json.loads(verification_result)
                    confidence = parsed.get("confidence", "High")
                except Exception:
                    parsed = None
                    confidence = "High"

                if confidence != "High":
                    # 再生成（厳格モードを適用）
                    strict_template = ct.SYSTEM_TEMPLATE_STRICT_RESPONSE + "\n\n" + ct.SYSTEM_TEMPLATE_BASIC_CONVERSATION
                    strict_chain = ft.create_chain(strict_template)
                    try:
                        new_response = strict_chain.predict(input=audio_input_text)
                        llm_response = new_response
                        st.info("応答を精度優先で再生成しました")
                    except Exception:
                        pass

                with st.expander("自動フィードバック（検証結果）"):
                    if 'verification_result' in locals():
                        try:
                            vr = json.loads(verification_result)
                        except Exception:
                            st.text("検証結果の解析に失敗しました。生データ:")
                            st.text(verification_result)
                        else:
                            # 表示: 信頼度・問題点・前提・修正済み回答・ソース
                            confidence = vr.get("confidence", "Unknown")
                            issues = vr.get("issues", []) or []
                            assumptions = vr.get("assumptions", []) or []
                            verified_answer = vr.get("verified_answer", "")
                            sources = vr.get("sources", []) or []

                            st.markdown(f"**信頼度:** {confidence}")
                            if issues:
                                st.markdown("**検出された問題:**")
                                for it in issues:
                                    st.markdown(f"- {it}")
                            else:
                                st.markdown("**検出された問題:** なし")

                            if assumptions:
                                st.markdown("**モデルの仮定:**")
                                for a in assumptions:
                                    st.markdown(f"- {a}")

                            if sources:
                                st.markdown("**参照ソース:**")
                                for s in sources:
                                    st.markdown(f"- {s}")
                            else:
                                st.markdown("**参照ソース:** なし")

                            if verified_answer:
                                st.markdown("**修正済み回答:**")
                                st.write(verified_answer)
                    else:
                        st.text("検証結果は利用できません")

                # 音声合成
                llm_response_audio = st.session_state.openai_obj.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=llm_response
                )
                audio_output_file_path = f"{ct.AUDIO_OUTPUT_DIR}/audio_output_{int(time.time())}.wav"
                ft.save_to_wav(llm_response_audio.content, audio_output_file_path)

            ft.play_wav(audio_output_file_path, speed=st.session_state.speed)

            with st.chat_message("assistant", avatar=ct.AI_ICON_PATH):
                st.markdown(llm_response)

            st.session_state.messages.append({"role": "user", "content": audio_input_text})
            st.session_state.messages.append({"role": "assistant", "content": llm_response})

        else:
            # テキストベースの活動（ロールプレイ等）
            if activity_en == "Roleplay":
                level = st.selectbox("レベル", ["Beginner", "Intermediate", "Advanced"], index=0)
                scenario = st.text_input("Scenario (短く):", value="Order food at a cafe")
                input_str = f"LEVEL: {level}\nSCENARIO: {scenario}"
                template = ct.SYSTEM_TEMPLATE_ROLEPLAY
            elif activity_en == "Phrase Drill":
                level = st.selectbox("レベル", ["Beginner", "Intermediate", "Advanced"], index=0, key="phrase_level")
                target_phrase = st.text_input("Target phrase:", value="Can I get the check, please?")
                input_str = f"target_phrase: {target_phrase}\nlevel: {level}"
                template = ct.SYSTEM_TEMPLATE_TARGET_PHRASE_DRILL
            elif activity_en == "Small Talk":
                level = st.selectbox("レベル", ["Beginner", "Intermediate", "Advanced"], index=0, key="smalltalk_level")
                topic = st.text_input("Topic:", value="weekend plans")
                input_str = f"topic: {topic}\nlevel: {level}"
                template = ct.SYSTEM_TEMPLATE_SOCIAL_SMALLTALK
            elif activity_en == "Pronunciation Tip":
                level = st.selectbox("レベル", ["Beginner", "Intermediate", "Advanced"], index=0, key="pron_level")
                word = st.text_input("Word or short phrase:", value="thought")
                input_str = f"{word}\nlevel: {level}"
                template = ct.SYSTEM_TEMPLATE_PRONUNCIATION_TIPS
            elif activity_en == "Practice Goal":
                goal = st.text_input("Practice goal:", value="introduce myself")
                input_str = f"goal: {goal}"
                template = ct.SYSTEM_TEMPLATE_PRACTICE_GOAL
            else:
                input_str = ""
                template = ct.SYSTEM_TEMPLATE_BASIC_CONVERSATION

            if st.button("実行", key="activity_run"):
                # 実行ボタンが押されたら履歴をクリアして新しい活動を開始
                st.session_state.messages = []
                with st.spinner('応答生成中...'):
                    chain = ft.create_chain(template)
                    try:
                        response_text = chain.predict(input=input_str)
                    except Exception as e:
                        response_text = f"Error: {e}"

                with st.chat_message("assistant", avatar=ct.AI_ICON_PATH):
                    st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

                try:
                    llm_response_audio = st.session_state.openai_obj.audio.speech.create(
                        model="tts-1",
                        voice="alloy",
                        input=response_text
                    )
                    audio_output_file_path = f"{ct.AUDIO_OUTPUT_DIR}/audio_output_{int(time.time())}.wav"
                    ft.save_to_wav(llm_response_audio.content, audio_output_file_path)
                    ft.play_wav(audio_output_file_path, speed=st.session_state.speed)
                except Exception:
                    pass


    # モード：「シャドーイング」
    # 「シャドーイング」ボタン押下時か、「英会話開始」ボタン押下時
    if st.session_state.mode == ct.MODE_2 and (st.session_state.shadowing_button_flg or st.session_state.shadowing_count == 0 or st.session_state.shadowing_audio_input_flg):
        if st.session_state.shadowing_first_flg:
            st.session_state.chain_create_problem = ft.create_chain(ct.SYSTEM_TEMPLATE_CREATE_PROBLEM)
            st.session_state.shadowing_first_flg = False
        
        if not st.session_state.shadowing_audio_input_flg:
            with st.spinner('問題文生成中...'):
                st.session_state.problem, llm_response_audio = ft.create_problem_and_play_audio()

        # 音声入力を受け取って音声ファイルを作成
        st.session_state.shadowing_audio_input_flg = True
        audio_input_file_path = f"{ct.AUDIO_INPUT_DIR}/audio_input_{int(time.time())}.wav"
        ft.record_audio(audio_input_file_path)
        st.session_state.shadowing_audio_input_flg = False

        with st.spinner('音声入力をテキストに変換中...'):
            # 音声入力ファイルから文字起こしテキストを取得
            transcript = ft.transcribe_audio(audio_input_file_path)
            audio_input_text = transcript.text

        # AIメッセージとユーザーメッセージの画面表示
        with st.chat_message("assistant", avatar=ct.AI_ICON_PATH):
            st.markdown(st.session_state.problem)
        with st.chat_message("user", avatar=ct.USER_ICON_PATH):
            st.markdown(audio_input_text)
        
        # LLMが生成した問題文と音声入力値をメッセージリストに追加
        st.session_state.messages.append({"role": "assistant", "content": st.session_state.problem})
        st.session_state.messages.append({"role": "user", "content": audio_input_text})

        with st.spinner('評価結果の生成中...'):
            if st.session_state.shadowing_evaluation_first_flg:
                system_template = ct.SYSTEM_TEMPLATE_EVALUATION.format(
                    llm_text=st.session_state.problem,
                    user_text=audio_input_text
                )
                st.session_state.chain_evaluation = ft.create_chain(system_template)
                st.session_state.shadowing_evaluation_first_flg = False
            # 問題文と回答を比較し、評価結果の生成を指示するプロンプトを作成
            llm_response_evaluation = ft.create_evaluation()
        
        # 評価結果のメッセージリストへの追加と表示
        with st.chat_message("assistant", avatar=ct.AI_ICON_PATH):
            st.markdown(llm_response_evaluation)
        st.session_state.messages.append({"role": "assistant", "content": llm_response_evaluation})
        st.session_state.messages.append({"role": "other"})
        
        # 各種フラグの更新
        st.session_state.shadowing_flg = True
        st.session_state.shadowing_count += 1

        # 「シャドーイング」ボタンを表示するために再描画
        st.rerun()