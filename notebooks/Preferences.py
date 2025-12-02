import pandas as pd
import numpy as np


# ----------------- Load CSV -----------------
dfbooks = pd.read_csv("Books_clean.csv")
dfbooks = dfbooks.replace('', None)
dfbooks.replace([np.inf, -np.inf], np.nan, inplace=True)

dfratings = pd.read_csv("Ratings_clean.csv")
dfratings = dfratings.replace('', None)
dfratings.replace([np.inf, -np.inf], np.nan, inplace=True)

dfusers = pd.read_csv("Users_clean.csv")
dfusers = dfusers.replace('', None)
dfusers.replace([np.inf, -np.inf], np.nan, inplace=True)

df = dfratings.merge(dfbooks, on='ISBN').merge(dfusers, on='User-ID')

#PREFERENCE FAVORITE BOOK ##################################################################
 # Juntar ratings com os dados dos usuários
#dfratings = dfratings.merge(dfusers, on='User-ID')
# Juntar ratings com o nome dos livros
#dfratings = dfratings.merge(dfbooks, on='ISBN')

# Para cada usuário, escolher o livro com maior rating
idx = df.groupby('User-ID')['Book-Rating'].idxmax()
top_books = df.loc[idx, ['User-ID', 'ISBN', 'Book-Title', 'Book-Rating']].reset_index(drop=True)
    
#print(top_books[['User-ID', 'ISBN', 'Book-Title', 'Book-Rating']])

#Falta colocar no mongoDB
#docs = top_books.to_dict(orient='records')
    
    # Conectar ao MongoDB e inserir
#client = MongoClient(mongo_uri)
#db = client[db_name]
#collection = db[collection_name]
#collection.insert_many(docs)

#PREFERENCE preferred_genres##################################################################

count = df.groupby(['User-ID', 'categories']).size().reset_index(name='rating_count')

# Para cada usuário, selecionar a categoria com maior contagem
idx = count.groupby('User-ID')['rating_count'].idxmax()
top_categorias = count.loc[idx].reset_index(drop=True)

#print(top_categorias)

#FALTA INSERT PARA O MONGO

#PREFERENCE preferred_genres##################################################################

count = df.groupby(['User-ID', 'Book-Author']).size().reset_index(name='rating_count')

# Para cada usuário, selecionar a categoria com maior contagem
idx = count.groupby('User-ID')['rating_count'].idxmax()
top_authors = count.loc[idx].reset_index(drop=True)

#print(top_authors)

#FALTA INSERT PARA O MONGO

#PREFERENCE preferred_publishers##################################################################

count = df.groupby(['User-ID', 'Publisher']).size().reset_index(name='rating_count')

# Para cada usuário, selecionar a categoria com maior contagem
idx = count.groupby('User-ID')['rating_count'].idxmax()
top_publishers = count.loc[idx].reset_index(drop=True)

#print(top_publishers)

#PREFERENCE preferred_publishers##################################################################

count = df.groupby(['User-ID', 'Year-Of-Publication']).size().reset_index(name='rating_count')

# Para cada usuário, selecionar a categoria com maior contagem
idx = count.groupby('User-ID')['rating_count'].idxmax()
top_publishers = count.loc[idx].reset_index(drop=True)

print(top_publishers)

#FALTA INSERT PARA O MONGO
