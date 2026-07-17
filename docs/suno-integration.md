# Integração com Suno Analítica

A rota pública adotada para descoberta é:

`https://www.suno.com.br/analitica/acoes/<ticker>/`

O coletor procura a seção de notícias da companhia, segue somente links públicos e mantém limite de requisições e cache por URL e conteúdo. A Suno é uma fonte de contexto, não a fonte dos números contábeis do projeto.

A aplicação não copia nem distribui matérias. Armazena apenas metadados, link para a publicação original e síntese própria. O corpo da notícia é descartado após a leitura transitória.
