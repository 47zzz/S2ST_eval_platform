import pandas as pd
import json
import matplotlib.pyplot as plt
import seaborn as sns
import os
import glob

def load_all_jsonl(directory, phase):
    """
    從指定目錄讀取所有符合特定 phase (ab 或 mos) 的 jsonl 檔案，
    檔名規則假設包含 f"_{phase}_" (例如 id_mos_timestamp.jsonl 或 id_ab_timestamp.jsonl)
    """
    data = []
    # 尋找目錄下所有 .jsonl 結尾的檔案
    filepaths = glob.glob(os.path.join(directory, "*.jsonl"))
    
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        # 篩選檔名中包含對應 phase 的檔案
        if f"_{phase}_" in filename:
            print(f"載入檔案: {filename}")
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        # 在資料中加入來源檔名，方便未來追查
                        row = json.loads(line)
                        row['source_file'] = filename
                        data.append(row)
                        
    if not data:
        print(f"⚠️ 在 {directory} 中沒有找到包含 '{phase}' 的 .jsonl 檔案。")
        return pd.DataFrame()
        
    return pd.DataFrame(data)

def analyze_ab_test(df_ab):
    """解析 A/B Test 結果，還原選項真實對應的模型並計算輸贏"""
    if df_ab.empty:
        return pd.DataFrame()
        
    results = []
    for _, row in df_ab.iterrows():
        pref = row.get('preference')
        
        # 決定勝利者是誰
        if pref == 'A':
            winner = row.get('display_a_is')
        elif pref == 'B':
            winner = row.get('display_b_is')
        else:
            winner = 'Tie' # 平手
            
        results.append({
            'subject_id': row.get('subject_id'),
            'emotion': row.get('emotion'),
            'model_a': row.get('model_a'),
            'model_b': row.get('model_b'),
            'winner': winner,
            'source_file': row.get('source_file')
        })
    return pd.DataFrame(results)

def plot_ab_charts(df_ab_results, output_dir):
    """繪製 A/B Test 統計圖表"""
    if df_ab_results.empty:
        return
        
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 總體勝率圓餅圖 (Overall Win Rate)
    plt.figure(figsize=(8, 6))
    win_counts = df_ab_results['winner'].value_counts()
    
    # 動態設定顏色，讓同一個模型的顏色一致
    color_map = {
        'gen_MoE_top5_attention': '#66b3ff',
        'gen_ours_100hr': '#ff9999',
        'Tie': '#d9d9d9'
    }
    # 若出現其他模型，給予預設顏色
    colors = [color_map.get(w, '#cccccc') for w in win_counts.index]
    
    win_counts.plot(kind='pie', autopct='%1.1f%%', startangle=90, colors=colors, wedgeprops={'edgecolor': 'black'})
    plt.title('A/B Test Overall Preference')
    plt.ylabel('')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'ab_test_overall.png'), dpi=300)
    plt.close()

    # 2. 各情緒的勝率長條圖 (Win Rate by Emotion)
    plt.figure(figsize=(10, 6))
    emotion_win = pd.crosstab(df_ab_results['emotion'], df_ab_results['winner'], normalize='index') * 100
    
    # 將現有資料中的模型套用顏色設定
    plot_cols = emotion_win.columns.tolist()
    emotion_colors = [color_map.get(col, '#cccccc') for col in plot_cols]
    
    ax = emotion_win.plot(kind='bar', stacked=True, figsize=(10, 6), color=emotion_colors, edgecolor='black')
    plt.title('A/B Test Preference by Emotion')
    plt.ylabel('Percentage (%)')
    plt.xlabel('Emotion')
    plt.xticks(rotation=45)
    
    # 調整圖例位置
    plt.legend(title='Winner', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'ab_test_by_emotion.png'), dpi=300)
    plt.close()

def plot_mos_charts(df_mos, output_dir):
    """繪製 MOS 測試統計圖表。包含 Naturalness 與 Emotion Similarity"""
    if df_mos.empty:
        return
        
    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid")
    
    # 計算各模型的平均數
    avg_scores = df_mos.groupby('model_folder')[['naturalness', 'emotion_sim']].mean().reset_index()
    # 依照 Emotion Sim 分數遞減排序，讓圖表比較好看
    avg_scores = avg_scores.sort_values(by='emotion_sim', ascending=False)
    model_order = avg_scores['model_folder'].tolist()
    
    # 1. 兩種分數的平均值長條圖 (Barplot of Average Scores)
    avg_scores_melted = avg_scores.melt(id_vars='model_folder', var_name='Metric', value_name='Average Score')
    plt.figure(figsize=(12, 6))
    sns.barplot(data=avg_scores_melted, x='model_folder', y='Average Score', hue='Metric', palette='Set2')
    plt.title('MOS Test: Average Scores by Model')
    plt.xticks(rotation=45, ha='right')
    plt.ylim(0, 5) # 分數滿分 5
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'mos_average_scores.png'), dpi=300)
    plt.close()

    # 2. 自然度箱型圖 (Boxplot of Naturalness)
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df_mos, x='model_folder', y='naturalness', order=model_order, palette='Pastel1')
    plt.title('MOS Test: Naturalness Scores Distribution')
    plt.xticks(rotation=45, ha='right')
    plt.ylim(0.5, 5.5)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'mos_naturalness_boxplot.png'), dpi=300)
    plt.close()

    # 3. 情緒相似度箱型圖 (Boxplot of Emotion Similarity)
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df_mos, x='model_folder', y='emotion_sim', order=model_order, palette='Pastel2')
    plt.title('MOS Test: Emotion Similarity Scores Distribution')
    plt.xticks(rotation=45, ha='right')
    plt.ylim(0.5, 5.5)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'mos_emotion_sim_boxplot.png'), dpi=300)
    plt.close()

def main():
    # ==== 請設定包含所有 jsonl 檔案的資料夾路徑 ====
    target_dir = '/Users/477z/Desktop/saved'
    output_dir = os.path.join(target_dir, 'charts')
    
    print(f"準備掃描目錄：{target_dir}")
    
    # 讀取所有的 AB Test 記錄
    print("\n--- 讀取 A/B Test 資料 ---")
    df_ab = load_all_jsonl(target_dir, phase='ab')
    if not df_ab.empty:
        print(f"共讀取到 {len(df_ab)} 筆 A/B 測試記錄（包含多位受試者）")
        df_ab_results = analyze_ab_test(df_ab)
        plot_ab_charts(df_ab_results, output_dir)
        print("✅ A/B Test 圖表繪製完成！")
    
    # 讀取所有的 MOS 記錄
    print("\n--- 讀取 MOS 資料 ---")
    df_mos = load_all_jsonl(target_dir, phase='mos')
    if not df_mos.empty:
        print(f"共讀取到 {len(df_mos)} 筆 MOS 測試記錄（包含多位受試者）")
        plot_mos_charts(df_mos, output_dir)
        print("✅ MOS Test 圖表繪製完成！")
        
    print(f"\n🎉 執行完畢！所有產生圖表已存至：{output_dir}")

if __name__ == '__main__':
    main()
