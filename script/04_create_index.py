#!/usr/bin/env python
# Auto-generated from 04_create_index.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os
from dotenv import load_dotenv
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchField, SearchFieldDataType, SearchIndex,
    VectorSearch, HnswAlgorithmConfiguration, HnswParameters, VectorSearchProfile,
    AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters,
    ScalarQuantizationCompression, ScalarQuantizationParameters, RescoringOptions,
    SemanticConfiguration, SemanticPrioritizedFields, SemanticField, SemanticSearch,
)
import utils_cc as U

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present

name_prefix = os.environ['NAME_PREFIX']
index_name = f'{name_prefix}-index'
semantic_config_name = os.getenv('AZURE_SEARCH_SEMANTIC_CONFIGURATION', f'{name_prefix}-semantic-configuration')

search_endpoint = os.environ['AZURE_SEARCH_ENDPOINT']
aoai_endpoint = os.environ['AZURE_OPENAI_ENDPOINT']
embedding_deployment = os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', 'text-embedding-3-large')
embedding_model = os.getenv('AZURE_OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large')
embedding_dimensions = int(os.getenv('AZURE_OPENAI_EMBEDDING_DIMENSIONS', '3072'))

credential = U.get_search_credential()
print('index:', index_name, '| semantic:', semantic_config_name)

fields = [
    SearchField(name='uid', type=SearchFieldDataType.String, key=True,
                searchable=True, filterable=False, retrievable=True, stored=True,
                sortable=True, facetable=False, analyzer_name='keyword'),
    SearchField(name='snippet_parent_id', type=SearchFieldDataType.String,
                searchable=False, filterable=True, retrievable=True, stored=True,
                sortable=False, facetable=False),
    SearchField(name='blob_url', type=SearchFieldDataType.String,
                searchable=False, filterable=True, retrievable=True, stored=True,
                sortable=False, facetable=False),
    SearchField(name='snippet', type=SearchFieldDataType.String,
                searchable=True, filterable=False, retrievable=True, stored=True,
                sortable=False, facetable=False, analyzer_name='ja.microsoft'),
    SearchField(name='image_snippet_parent_id', type=SearchFieldDataType.String,
                searchable=False, filterable=True, retrievable=True, stored=True,
                sortable=False, facetable=False),
    SearchField(name='snippet_vector',
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True, filterable=False, retrievable=True, stored=True,
                sortable=False, facetable=False,
                vector_search_dimensions=embedding_dimensions,
                vector_search_profile_name=f'{name_prefix}-vector-search-profile'),
]

vector_search = VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(
            name=f'{name_prefix}-vector-search-algorithm',
            parameters=HnswParameters(metric='cosine', m=4, ef_construction=400, ef_search=500),
        ),
    ],
    profiles=[
        VectorSearchProfile(
            name=f'{name_prefix}-vector-search-profile',
            algorithm_configuration_name=f'{name_prefix}-vector-search-algorithm',
            vectorizer_name=f'{name_prefix}-vectorizer',
            compression_name=f'{name_prefix}-vector-search-scalar-quantization',
        ),
    ],
    vectorizers=[
        AzureOpenAIVectorizer(
            vectorizer_name=f'{name_prefix}-vectorizer',
            parameters=AzureOpenAIVectorizerParameters(
                resource_url=aoai_endpoint,
                deployment_name=embedding_deployment,
                model_name=embedding_model,
                # No api_key -> search service managed identity is used.
            ),
        ),
    ],
    compressions=[
        ScalarQuantizationCompression(
            compression_name=f'{name_prefix}-vector-search-scalar-quantization',
            parameters=ScalarQuantizationParameters(quantized_data_type='int8'),
            rescoring_options=RescoringOptions(
                enable_rescoring=True, default_oversampling=4.0,
                rescore_storage_method='preserveOriginals'),
        ),
    ],
)

semantic_search = SemanticSearch(
    default_configuration_name=semantic_config_name,
    configurations=[
        SemanticConfiguration(
            name=semantic_config_name,
            prioritized_fields=SemanticPrioritizedFields(
                content_fields=[SemanticField(field_name='snippet')]),
        ),
    ],
)

index_client = SearchIndexClient(endpoint=search_endpoint, credential=credential)
index = SearchIndex(
    name=index_name,
    description=f"Search index for knowledge source '{name_prefix}'",
    fields=fields,
    vector_search=vector_search,
    semantic_search=semantic_search,
)
result = index_client.create_or_update_index(index)
print(f"Index '{result.name}' created or updated.")
