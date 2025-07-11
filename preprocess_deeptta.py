import pandas as pd
import numpy as np
import os

def preprocess_deeptta_data(
    drug_response_path='/workspace/data/drug_IC50_raw_data.csv', 
    gene_expr_path='/workspace/data/gene_expression_raw_data.txt',
    output_dir='/workspace/data/deeptta_processed'
):
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load Drug Response Data
    drug_df = pd.read_csv(drug_response_path)
    
    # Select relevant columns and perform initial cleaning
    drug_df = drug_df[['COSMIC_ID', 'DRUG_NAME', 'LN_IC50', 'AUC']]
    drug_df = drug_df.dropna(subset=['COSMIC_ID', 'DRUG_NAME', 'LN_IC50', 'AUC'])

    # 2. Load Gene Expression Data
    gene_expr_df = pd.read_csv(gene_expr_path, sep='\t')
    
    # Transform gene expression data from wide to long format
    gene_expr_df = gene_expr_df.melt(
        id_vars=['GENE_SYMBOLS', 'GENE_title'], 
        var_name='COSMIC_ID', 
        value_name='GENE_EXPRESSION'
    )
    gene_expr_df['COSMIC_ID'] = gene_expr_df['COSMIC_ID'].str.replace('DATA.', '')

    # 3. Get Common Cell Lines
    common_cosmic_ids = set(drug_df['COSMIC_ID']) & set(gene_expr_df['COSMIC_ID'])
    
    # Filter datasets to common cell lines
    drug_df = drug_df[drug_df['COSMIC_ID'].isin(common_cosmic_ids)]
    gene_expr_df = gene_expr_df[gene_expr_df['COSMIC_ID'].isin(common_cosmic_ids)]

    # 4. Pivot Gene Expression Data
    gene_expr_pivot = gene_expr_df.pivot_table(
        index='COSMIC_ID', 
        columns='GENE_SYMBOLS', 
        values='GENE_EXPRESSION', 
        aggfunc='first'
    ).reset_index()

    # 5. Merge Drug Response with Gene Expression
    merged_df = pd.merge(drug_df, gene_expr_pivot, on='COSMIC_ID')

    # 6. Add placeholder SMILES (you'll need to replace this with actual SMILES data)
    merged_df['SMILES'] = 'CC(=O)OC1=CC=CC=C1C(=O)O'  # Example: Aspirin SMILES

    # 7. Save Processed Files
    merged_df.to_csv(os.path.join(output_dir, 'drug_response_gene_expr.csv'), index=False)
    gene_expr_pivot.to_csv(os.path.join(output_dir, 'gene_expression_processed.csv'), index=False)

    print("Data preprocessing completed successfully.")
    print(f"Processed data saved in {output_dir}")
    print(f"Number of cell lines: {len(common_cosmic_ids)}")
    print(f"Number of drugs: {merged_df['DRUG_NAME'].nunique()}")

if __name__ == '__main__':
    preprocess_deeptta_data()