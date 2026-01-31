Build a production-ready command line tool in go called `og` which uses xref data from an opengrok server to trace sources -> sinks in a codebase and illustrate them visually in a human-friendly format.

* You can test against `https://src.illumos.org/source/xref/illumos-gate/`
* Take as input a function to start from as the source
* Return as output an html file with a creative, elegant UI with expand/collapse features to allow you explore the call graph from this source outward (get inspiration from other tools which do this)git 
* Add a 'depth' argument to limit how far the output goes (e.g. `--depth=3` will report the source, the functions it calls, and the ones those call)
* Include full robust testing to ensure that the output is sensible
* There are likely to be performance issues. Consider carefully how best to talk to the opengrok API so that you minimise the time it takes to build the graph
* You are done when the output of the tool is correct, human-friendly and can return correct results for up to --depth=7 in a sensible time period.