## LiDS Ontology

<section id="metadata">
    <h4 style="display:none;">Metadata</h4>
    <dl>
        <dt>URI</dt>
        <dd><code>http://sack.local/ontology/</code></dd>
        <dt>Ontology RDF</dt>
        <dd><a href="data_file.ttl">RDF (turtle)</a></dd>
    </dl>
</section>
<section id="toc">
    <h4>Table of Contents</h4>
    <ol>
        <li><a href="#classes">Classes</a></li>
        <li><a href="#objectproperties">Object Properties</a></li>
        <li><a href="#datatypeproperties">Datatype Properties</a></li>
        <li><a href="#namespaces">Namespaces</a></li>
        <li><a href="#legend">Legend</a></li>
    </ol>
</section>
  <section id="classes">
    <h4>Classes <span style="float:right; font-size:smaller;"><a href="">&uparrow;</a></span></h4>
    <ul class="hlist">
        <li><a href="#API">API</a></li>
        <li><a href="#Class">Class</a></li>
        <li><a href="#Column">Column</a></li>
        <li><a href="#DataItem">DataItem</a></li>
        <li><a href="#DataScienceItem">DataScienceItem</a></li>
        <li><a href="#Dataset">Dataset</a></li>
        <li><a href="#Function">Function</a></li>
        <li><a href="#Library">Library</a></li>
        <li><a href="#Package">Package</a></li>
        <li><a href="#Pipeline">Pipeline</a></li>
        <li><a href="#PipelineItem">PipelineItem</a></li>
        <li><a href="#Source">Source</a></li>
        <li><a href="#Statement">Statement</a></li>
        <li><a href="#Table">Table</a></li>
    </ul>
    <div class="entity class" id="API">
        <h3>API<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/API</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/PipelineItem">PipelineItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>Sub-classes</th>
                <td>
                    <a href="http://sack.local/ontology/Library">Library</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Package">Package</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Class">Class</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Function">Function</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsAPI">http://sack.local/ontology/pipeline/callsAPI</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Class">
        <h3>Class<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Class</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/API">API</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsClass">http://sack.local/ontology/pipeline/callsClass</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Column">
        <h3>Column<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Column</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/DataItem">DataItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In domain of</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasFilePath">http://sack.local/ontology/data/hasFilePath</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasSemanticSimilarity">http://sack.local/ontology/data/hasSemanticSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasTotalValueCount">http://sack.local/ontology/data/hasTotalValueCount</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasContentSimilarity">http://sack.local/ontology/data/hasContentSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasDeepPrimaryKeyForeignKeySimilarity">http://sack.local/ontology/data/hasDeepPrimaryKeyForeignKeySimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasMissingValueCount">http://sack.local/ontology/data/hasMissingValueCount</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasPrimaryKeyForeignKeySimilarity">http://sack.local/ontology/data/hasPrimaryKeyForeignKeySimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasDistinctValueCount">http://sack.local/ontology/data/hasDistinctValueCount</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasInclusionDependency">http://sack.local/ontology/data/hasInclusionDependency</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasMedianValue">http://sack.local/ontology/data/hasMedianValue</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasMaxValue">http://sack.local/ontology/data/hasMaxValue</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasDeepEmbeddingContentSimilarity">http://sack.local/ontology/data/hasDeepEmbeddingContentSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasDataType">http://sack.local/ontology/data/hasDataType</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasMinValue">http://sack.local/ontology/data/hasMinValue</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasDeepEmbeddingContentSimilarity">http://sack.local/ontology/data/hasDeepEmbeddingContentSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasInclusionDependency">http://sack.local/ontology/data/hasInclusionDependency</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasContentSimilarity">http://sack.local/ontology/data/hasContentSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasDeepPrimaryKeyForeignKeySimilarity">http://sack.local/ontology/data/hasDeepPrimaryKeyForeignKeySimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasPrimaryKeyForeignKeySimilarity">http://sack.local/ontology/data/hasPrimaryKeyForeignKeySimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/readsColumn">http://sack.local/ontology/pipeline/readsColumn</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasSemanticSimilarity">http://sack.local/ontology/data/hasSemanticSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="DataItem">
        <h3>DataItem<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/DataItem</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/DataScienceItem">DataScienceItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>Sub-classes</th>
                <td>
                    <a href="http://sack.local/ontology/Dataset">Dataset</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Table">Table</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Source">Source</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/reads">http://sack.local/ontology/pipeline/reads</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="DataScienceItem">
        <h3>DataScienceItem<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/DataScienceItem</code></td>
            </tr>
            <tr>
                <th>Sub-classes</th>
                <td>
                    <a href="http://sack.local/ontology/PipelineItem">PipelineItem</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/DataItem">DataItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In domain of</th>
                <td>
                    <a href="http://sack.local/ontology/isPartOf">isPartOf</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/isPartOf">isPartOf</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Dataset">
        <h3>Dataset<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Dataset</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/DataItem">DataItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In domain of</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasDatasetSimilarity">http://sack.local/ontology/data/hasDatasetSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasDatasetSimilarity">http://sack.local/ontology/data/hasDatasetSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Function">
        <h3>Function<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Function</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/API">API</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsFunction">http://sack.local/ontology/pipeline/callsFunction</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Library">
        <h3>Library<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Library</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/API">API</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsLibrary">http://sack.local/ontology/pipeline/callsLibrary</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Package">
        <h3>Package<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Package</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/API">API</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsPackage">http://sack.local/ontology/pipeline/callsPackage</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Pipeline">
        <h3>Pipeline<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Pipeline</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/PipelineItem">PipelineItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In domain of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/isWrittenOn">http://sack.local/ontology/pipeline/isWrittenOn</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasSourceURL">http://sack.local/ontology/pipeline/hasSourceURL</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasVotes">http://sack.local/ontology/pipeline/hasVotes</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasScore">http://sack.local/ontology/pipeline/hasScore</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasTag">http://sack.local/ontology/pipeline/hasTag</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/isWrittenBy">http://sack.local/ontology/pipeline/isWrittenBy</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="PipelineItem">
        <h3>PipelineItem<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/PipelineItem</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/DataScienceItem">DataScienceItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>Sub-classes</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup><br/>
                    <a href="http://sack.local/ontology/API">API</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Source">
        <h3>Source<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Source</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/DataItem">DataItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Statement">
        <h3>Statement<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Statement</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/PipelineItem">PipelineItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In domain of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/reads">http://sack.local/ontology/pipeline/reads</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/callsPackage">http://sack.local/ontology/pipeline/callsPackage</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasNextStatement">http://sack.local/ontology/pipeline/hasNextStatement</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/readsTable">http://sack.local/ontology/pipeline/readsTable</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasDataFlowTo">http://sack.local/ontology/pipeline/hasDataFlowTo</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/readsColumn">http://sack.local/ontology/pipeline/readsColumn</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/inControlFlow">http://sack.local/ontology/pipeline/inControlFlow</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/callsLibrary">http://sack.local/ontology/pipeline/callsLibrary</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/flowsTo">http://sack.local/ontology/pipeline/flowsTo</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/callsFunction">http://sack.local/ontology/pipeline/callsFunction</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/callsAPI">http://sack.local/ontology/pipeline/callsAPI</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/callsClass">http://sack.local/ontology/pipeline/callsClass</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasParameter">http://sack.local/ontology/pipeline/hasParameter</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasText">http://sack.local/ontology/pipeline/hasText</a><sup class="sup-dp" title="datatype property">dp</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/hasDataFlowTo">http://sack.local/ontology/pipeline/hasDataFlowTo</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/flowsTo">http://sack.local/ontology/pipeline/flowsTo</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/pipeline/hasNextStatement">http://sack.local/ontology/pipeline/hasNextStatement</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity class" id="Table">
        <h3>Table<sup title="class" class="sup-c">c</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/Table</code></td>
            </tr>
            <tr>
                <th>Super-classes</th>
                <td>
                    <a href="http://sack.local/ontology/DataItem">DataItem</a><sup class="sup-c" title="class">c</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In domain of</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasTableSimilarity">http://sack.local/ontology/data/hasTableSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
            <tr>
                <th>In range of</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/readsTable">http://sack.local/ontology/pipeline/readsTable</a><sup class="sup-op" title="object property">op</sup><br/>
                    <a href="http://sack.local/ontology/data/hasTableSimilarity">http://sack.local/ontology/data/hasTableSimilarity</a><sup class="sup-op" title="object property">op</sup><br/>
                </td>
            </tr>
        </table>
    </div>
</section>
<section id="objectproperties">
    <h4>Object Properties <span style="float:right; font-size:smaller;"><a href="">&uparrow;</a></span></h4>
    <ul class="hlist">
        <li><a href="#hasColumnSimilarity">hasColumnSimilarity</a></li>
        <li><a href="#hasContentSimilarity">hasContentSimilarity</a></li>
        <li><a href="#hasDatasetSimilarity">hasDatasetSimilarity</a></li>
        <li><a href="#hasDeepEmbeddingContentSimilarity">hasDeepEmbeddingContentSimilarity</a></li>
        <li><a href="#hasDeepPrimaryKeyForeignKeySimilarity">hasDeepPrimaryKeyForeignKeySimilarity</a></li>
        <li><a href="#hasInclusionDependency">hasInclusionDependency</a></li>
        <li><a href="#hasPrimaryKeyForeignKeySimilarity">hasPrimaryKeyForeignKeySimilarity</a></li>
        <li><a href="#hasSemanticSimilarity">hasSemanticSimilarity</a></li>
        <li><a href="#hasTableSimilarity">hasTableSimilarity</a></li>
        <li><a href="#isPartOf">isPartOf</a></li>
        <li><a href="#callsAPI">callsAPI</a></li>
        <li><a href="#callsClass">callsClass</a></li>
        <li><a href="#callsFunction">callsFunction</a></li>
        <li><a href="#callsLibrary">callsLibrary</a></li>
        <li><a href="#callsPackage">callsPackage</a></li>
        <li><a href="#flowsTo">flowsTo</a></li>
        <li><a href="#hasDataFlowTo">hasDataFlowTo</a></li>
        <li><a href="#hasNextStatement">hasNextStatement</a></li>
        <li><a href="#reads">reads</a></li>
        <li><a href="#readsColumn">readsColumn</a></li>
        <li><a href="#readsTable">readsTable</a></li>
    </ul>
    <div class="entity property" id="hasColumnSimilarity">
        <h3>hasColumnSimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasColumnSimilarity</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasContentSimilarity">
        <h3>hasContentSimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasContentSimilarity</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasDatasetSimilarity">
        <h3>hasDatasetSimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasDatasetSimilarity</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Dataset">Dataset</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Dataset">Dataset</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasDeepEmbeddingContentSimilarity">
        <h3>hasDeepEmbeddingContentSimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasDeepEmbeddingContentSimilarity</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasDeepPrimaryKeyForeignKeySimilarity">
        <h3>hasDeepPrimaryKeyForeignKeySimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasDeepPrimaryKeyForeignKeySimilarity</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasInclusionDependency">
        <h3>hasInclusionDependency<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasInclusionDependency</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasPrimaryKeyForeignKeySimilarity">
        <h3>hasPrimaryKeyForeignKeySimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasPrimaryKeyForeignKeySimilarity</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasSemanticSimilarity">
        <h3>hasSemanticSimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasSemanticSimilarity</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/data/hasColumnSimilarity">http://sack.local/ontology/data/hasColumnSimilarity</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasTableSimilarity">
        <h3>hasTableSimilarity<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasTableSimilarity</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Table">Table</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Table">Table</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="isPartOf">
        <h3>isPartOf<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/isPartOf</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/DataScienceItem">DataScienceItem</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/DataScienceItem">DataScienceItem</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="callsAPI">
        <h3>callsAPI<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/callsAPI</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://www.w3.org/2002/07/owl#topObjectProperty">owl:topObjectProperty</a>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/API">API</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="callsClass">
        <h3>callsClass<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/callsClass</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsAPI">http://sack.local/ontology/pipeline/callsAPI</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Class">Class</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="callsFunction">
        <h3>callsFunction<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/callsFunction</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsAPI">http://sack.local/ontology/pipeline/callsAPI</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Function">Function</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="callsLibrary">
        <h3>callsLibrary<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/callsLibrary</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsAPI">http://sack.local/ontology/pipeline/callsAPI</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Library">Library</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="callsPackage">
        <h3>callsPackage<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/callsPackage</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/callsAPI">http://sack.local/ontology/pipeline/callsAPI</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Package">Package</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="flowsTo">
        <h3>flowsTo<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/flowsTo</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasDataFlowTo">
        <h3>hasDataFlowTo<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasDataFlowTo</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/flowsTo">http://sack.local/ontology/pipeline/flowsTo</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasNextStatement">
        <h3>hasNextStatement<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasNextStatement</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/flowsTo">http://sack.local/ontology/pipeline/flowsTo</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="reads">
        <h3>reads<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/reads</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/DataItem">DataItem</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="readsColumn">
        <h3>readsColumn<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/readsColumn</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/reads">http://sack.local/ontology/pipeline/reads</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="readsTable">
        <h3>readsTable<sup title="object property" class="sup-op">op</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/readsTable</code></td>
            </tr>
            <tr>
                <th>Super-properties</th>
                <td>
                    <a href="http://sack.local/ontology/pipeline/reads">http://sack.local/ontology/pipeline/reads</a><sup class="sup-op" title="object property">op</sup>
                </td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Table">Table</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
</section>

<section id="datatypeproperties">
    <h4>Datatype Properties <span style="float:right; font-size:smaller;"><a href="">&uparrow;</a></span></h4>
    <ul class="hlist">
        <li><a href="#hasDataType">hasDataType</a></li>
        <li><a href="#hasDistinctValueCount">hasDistinctValueCount</a></li>
        <li><a href="#hasFilePath">hasFilePath</a></li>
        <li><a href="#hasMaxValue">hasMaxValue</a></li>
        <li><a href="#hasMedianValue">hasMedianValue</a></li>
        <li><a href="#hasMinValue">hasMinValue</a></li>
        <li><a href="#hasMissingValueCount">hasMissingValueCount</a></li>
        <li><a href="#hasTotalValueCount">hasTotalValueCount</a></li>
        <li><a href="#withCertainty">withCertainty</a></li>
        <li><a href="#hasParameter">hasParameter</a></li>
        <li><a href="#hasScore">hasScore</a></li>
        <li><a href="#hasSourceURL">hasSourceURL</a></li>
        <li><a href="#hasTag">hasTag</a></li>
        <li><a href="#hasText">hasText</a></li>
        <li><a href="#hasVotes">hasVotes</a></li>
        <li><a href="#inControlFlow">inControlFlow</a></li>
        <li><a href="#isWrittenBy">isWrittenBy</a></li>
        <li><a href="#isWrittenOn">isWrittenOn</a></li>
        <li><a href="#withParameterValue">withParameterValue</a></li>
    </ul>
    <div class="entity property" id="hasDataType">
        <h3>hasDataType<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasDataType</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasDistinctValueCount">
        <h3>hasDistinctValueCount<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasDistinctValueCount</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#int">xsd:int</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasFilePath">
        <h3>hasFilePath<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasFilePath</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasMaxValue">
        <h3>hasMaxValue<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasMaxValue</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#double">xsd:double</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasMedianValue">
        <h3>hasMedianValue<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasMedianValue</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#double">xsd:double</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasMinValue">
        <h3>hasMinValue<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasMinValue</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#double">xsd:double</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasMissingValueCount">
        <h3>hasMissingValueCount<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasMissingValueCount</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#int">xsd:int</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasTotalValueCount">
        <h3>hasTotalValueCount<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/hasTotalValueCount</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Column">Column</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#int">xsd:int</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="withCertainty">
        <h3>withCertainty<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/data/withCertainty</code></td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#double">xsd:double</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasParameter">
        <h3>hasParameter<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasParameter</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasScore">
        <h3>hasScore<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasScore</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#double">xsd:double</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasSourceURL">
        <h3>hasSourceURL<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasSourceURL</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasTag">
        <h3>hasTag<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasTag</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasText">
        <h3>hasText<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasText</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="hasVotes">
        <h3>hasVotes<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/hasVotes</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#int">xsd:int</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="inControlFlow">
        <h3>inControlFlow<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/inControlFlow</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Statement">Statement</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="isWrittenBy">
        <h3>isWrittenBy<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/isWrittenBy</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="isWrittenOn">
        <h3>isWrittenOn<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/isWrittenOn</code></td>
            </tr>
            <tr>
                <th>Domain(s)</th>
                <td>
                    <a href="http://sack.local/ontology/Pipeline">Pipeline</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
    <div class="entity property" id="withParameterValue">
        <h3>withParameterValue<sup title="datatype property" class="sup-dp">dp</sup></h3>
        <table>
            <tr>
                <th>URI</th>
                <td><code>http://sack.local/ontology/pipeline/withParameterValue</code></td>
            </tr>
            <tr>
                <th>Range(s)</th>
                <td>
                    <a href="http://www.w3.org/2001/XMLSchema#string">xsd:string</a><sup class="sup-c" title="class">c</sup>
                </td>
            </tr>
        </table>
    </div>
</section>

  
  <section id="namedindividuals">
    <h4>Named Individuals <span style="float:right; font-size:smaller;"><a href="">&uparrow;</a></span></h4>
    <ul class="hlist">
    </ul>
</section>
  
  <section id="namespaces">
    <h4>Namespaces <span style="float:right; font-size:smaller;"><a href="">&uparrow;</a></span></h4>
    <dl>
        <dt>:</dt>
        <dd><code>http://sack.local/ontology/</code></dd>
        <dt>owl</dt>
        <dd><code>http://www.w3.org/2002/07/owl#</code></dd>
        <dt>prov</dt>
        <dd><code>http://www.w3.org/ns/prov#</code></dd>
        <dt>rdf</dt>
        <dd><code>http://www.w3.org/1999/02/22-rdf-syntax-ns#</code></dd>
        <dt>rdfs</dt>
        <dd><code>http://www.w3.org/2000/01/rdf-schema#</code></dd>
        <dt>sdo</dt>
        <dd><code>https://schema.org/</code></dd>
        <dt>skos</dt>
        <dd><code>http://www.w3.org/2004/02/skos/core#</code></dd>
        <dt>xsd</dt>
        <dd><code>http://www.w3.org/2001/XMLSchema#</code></dd>
    </dl>
</section>
  <section id="legend">
      <h4>Legend</h4>
      <table class="entity">
          <tr><td><sup class="sup-c" title="Classes">c</sup></td><td>Classes</td></tr>
          <tr><td><sup class="sup-op" title="Object Properties">op</sup></td><td>Object Properties</td></tr>
          <tr><td><sup class="sup-fp" title="Functional Properties">fp</sup></td><td>Functional Properties</td></tr>
          <tr><td><sup class="sup-dp" title="Data Properties">dp</sup></td><td>Data Properties</td></tr>
          <tr><td><sup class="sup-ap" title="Annotation Properties">dp</sup></td><td>Annotation Properties</td></tr>
          <tr><td><sup class="sup-p" title="Properties">p</sup></td><td>Properties</td></tr>
          <tr><td><sup class="sup-ni" title="Named Individuals">ni</sup></td><td>Named Individuals</td></tr>
      </table>
  </section>
