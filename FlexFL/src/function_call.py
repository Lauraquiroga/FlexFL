import Levenshtein

"""
Implements all the helper functions that the LLM can call during both SR (Space Reduction) and 
LR (Localization Refinement) stages.
Utility functions to search, retrieve, and format method/class/path information from bug program files.
A way to simulate an "interactive code navigation" session for the LLM during multi-turn function-calling.
"""

def split4search(query):
    """
    Breaks method signatures down into searchable tokens.
    """
    if '(' not in query:
        querys = query.split('.')
    else:
        signature = query[query.find('(')+1:query.find(')')]
        method = query[:query.find('(')]
        querys = method.split('.') + [e.strip().split('.')[-1] for e in signature.split(',')]
    return querys

def fuzzy_search(query, choices):
    query = query.replace('#','.')
    query = query.replace('$','.')
    match_res = []
    querys = split4search(query)
    for choice in choices:
        match_choice = split4search(choice)
        flag = True
        for match_query in querys:
            if match_query not in match_choice:
                flag = False
                break
        if flag:
            match_res.append(choice)
    if len(match_res) == 0:
        if '(' in query:
            signature = query[query.find('(')+1:query.find(')')]
            query = query.split('(')[0]+'('+','.join([e.strip().split('.')[-1] for e in signature.split(',')])+')'
        distances = [(choice,Levenshtein.distance(query, choice)) for choice in choices]
        distances = sorted(distances, key=lambda x:x[1])
        for distance in distances:
            if distance[1] <= 5:
                match_res.append(distance[0])
            else:
                break
        if len(match_res) == 0:
            match_res = [distance[0] for distance in distances[:5]]
    return match_res
 
def get_code_snippet(bug, function, dataset):
    function = function.replace(', ',',')
    function = function.replace(' ,',',')
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
        methods = [e.strip() for e in f.readlines()]
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusRawMethodLevelGranularity') as f:
        codes = [e.strip() for e in f.readlines()]
    for method, code in zip(methods, codes):
        if method.replace('$','.',1) == function:
            return code
    methods = [method.replace('$','.',1) for method in methods]
    results = fuzzy_search(function, methods)
    if len(results) == 1:
        method = results[0]
        code = get_code_snippet(bug, method, dataset)
        return f"Do you mean `{method}`? Its code snippet is as follows.\n{code}"
    elif len(results) == 0:
        return "You provide a wrong method name. You can call `get_methods_of_class` first to get a right method name."
    else:
        results = '\n'.join(results)
        return "You provide a wrong method name. Please try the following method names.\n" + results

def get_paths(bug, dataset):
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
        paths = [e.strip().split('$')[0] for e in f.readlines()]
        # print(paths)
        paths = list(set(paths))
    return '\n'.join(sorted(paths))

def get_classes(bug, path_name, dataset):
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
        classes = ['.'.join(e.strip().split('$')[1].split('(')[0].split('.')[:-1]) for e in f.readlines() if e.startswith(path_name)]
        classes = list(set(classes))
    if len(classes) != 0:
        return '\n'.join(sorted(classes))
    else:
        with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
            paths = [e.strip().split('$')[0] for e in f.readlines()]
            # print(paths)
            paths = list(set(paths))
        results = fuzzy_search(path_name, paths)
        if len(results) == 1:
            return f"Do you mean `{results[0]}`? Its classes are as follows.\n{get_classes(bug, results[0], dataset)}"
        elif len(results) != 0:
            results = '\n'.join(sorted(results))
            return "You provide a wrong path name. Please try the following path names.\n" + results
        else:
            return "You provide a wrong path name. You can call `get_paths` first to get a right path name."

def get_methods(bug, class_name, dataset):
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
        methods = []
        for e in f.readlines():
            e = e.replace('$','.',1).strip()
            pos = e.find('(')
            class_ = '.'.join(e[:pos].split('.')[:-1])
            if class_ == class_name:
                methods.append(e[len(class_)+1:])
        methods = list(set(methods))
    if len(methods) != 0:
        return '\n'.join(sorted(methods))
    else:
        with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
            classes = ['.'.join(e.strip().replace('$','.',1).split('(')[0].split('.')[:-1]) for e in f.readlines()]
            classes = list(set(classes))
        results = fuzzy_search(class_name, classes)
        if len(results) == 1:
            print(results)
            return f"Do you mean `{results[0]}`? Its methods are as follows.\n{get_methods(bug, results[0], dataset)}"
        elif len(results) != 0:
            results = '\n'.join(sorted(results))
            return "You provide a wrong class name. Please try the following class names.\n" + results
        else:
            return "You provide a wrong class name. You can call `get_classes_of_path` first to get a right class name."


def find_class(bug, class_name, dataset):
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
        classes = ['.'.join(e.strip().replace('$','.',1).split('(')[0].split('.')[:-1]) for e in f.readlines()]
        classes = list(set(classes))
    if '.' in class_name:
        find = fuzzy_search(class_name, classes)
    else:
        find = [class_ for class_ in classes if class_.split('.')[-1] == class_name]
        if len(find) == 0:
            find = fuzzy_search(class_name, list(set([class_.split('.')[-1] for class_ in classes])))
            if len(find) == 1:
                return f"Do you mean `{find[0]}`? Its result of fuzzy search is as follows.\n{find_class(bug, find[0], dataset)}"
            else:
                results = '\n'.join(find)
                return f"Do not find `{class_name}` again because it is an invalid name. You can try the following names.\n{results}"
    return '\n'.join(sorted(find))

def find_method(bug, method_name, dataset):
    with open(f'../data/input/buggy_program/{dataset}/{bug}.corpusMappingWithPackageSeparatorMethodLevelGranularity') as f:
        methods = [e.strip().replace('$','.',1) for e in f.readlines()]
    find = []
    results = fuzzy_search(method_name,list(set(methods)))
    results = '\n'.join(results)
    return results
