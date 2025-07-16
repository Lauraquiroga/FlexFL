from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

import json
import os
from function_call import get_code_snippet, get_paths, get_classes, get_methods, find_class, find_method
import argparse

# Construction of open-source model
model_name = 'Qwen2'
######################### START

# 1. Build
device = "cuda"
tokenizer = AutoTokenizer.from_pretrained("./Qwen2-7B-Instruct", trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained("./Qwen2-7B-Instruct", trust_remote_code=True, torch_dtype="auto",device_map="auto")

# 2. Inference
def query(messages):
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text], return_tensors="pt").to(device)
    generated_ids = model.generate(
        model_inputs.input_ids,
        max_length=8192,
        do_sample=False
    )   
    generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)]
    return tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

######################### END
#From this point on it is the same as the pipeline.py file (for the llama3-8B-Instruct model)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='Defects4J', choices=['Defects4J', 'GHRB'])
    parser.add_argument('--input', default='All', choices=['bug_report', 'trigger_test', 'All'])
    parser.add_argument('--stage', default='LR', choices=['SR', 'LR']) ##### Note: Default here is LR stage
    parser.add_argument('--rank', default='All')
    args = parser.parse_args()
    dataset = args.dataset
    input_type = args.input
    stage = args.stage
    rank = args.rank

    with open(f'../data/bug_list/{dataset}/bug_list.txt') as f:
        bugs = [e.strip() for e in f.readlines()]

    if stage == 'SR':
        output_dir = f"{model_name}_{dataset}_SR" + ("_br" if input_type == 'bug_report' else "") + ("_tt" if input_type == 'trigger_test' else "")
    else:
        output_dir = f"{model_name}_{dataset}_{rank}"
    os.system(f'rm -rf ../res/{output_dir}')
    os.system(f'mkdir ../res/{output_dir}')
    
    for bug in bugs:
        if bug != 'Time-25': # To run only for 1 bug: Time-25
            continue
        print(bug)
        max_try = 10
        while max_try > 0:
            try:
                input_description = ""
                if (input_type == 'All' or input_type =='bug_report') and os.path.exists(f'../data/input/bug_reports/{dataset}/{bug}.json'):
                    input_type_a = "a bug report"
                    with open(f'../data/input/bug_reports/{dataset}/{bug}.json') as f:
                        bug_report = json.load(f)
                        if dataset == 'Defects4J':
                            input_description += f"The bug report is as follows:\n```\nTitle:{bug_report['title']}\nDescription:{bug_report['description']}\n```\n"
                        else:
                            input_description += f"The bug report is as follows:\n```\nTitle:{bug_report['title']}\nDescription:{bug_report['description_text']}\n```\n"
                else:
                    input_type_a = None
                if (input_type == 'All' or input_type =='trigger_test') and os.path.exists(f'../data/input/trigger_tests/{dataset}/{bug}.txt'):
                    if input_type_a:
                        input_type_a += ", a trigger test"
                    else:
                        input_type_a = "a trigger test"
                    with open(f'../data/input/trigger_tests/{dataset}/{bug}.txt') as f:
                        trigger_test = f.read()
                        input_description += f"The trigger test is as follows:\n```\n{trigger_test}\n```\n"
                input_type_the = input_type_a.replace('a', 'the')
                if stage == 'SR':
                    functions = "\nFunction calls you can use are as follows.\n\
* find_class(`class_name`) -> Find a class in the bug report by fuzzy search. `class_name` -> The name of the class. *\n\
* find_method(`method_name`) -> Find a method in the bug report by fuzzy search. `method_name` -> The name of the method. *\n\
* get_paths() -> Get the paths of the java software system. *\n\
* get_classes_of_path(`path_name`) -> Get the classes in the path of the java software system. `path_name` -> The accurate name of the path which can be accessed by function call `get_paths`. *\n\
* get_methods_of_class(`class_name`) -> Get the methods belonging to the class of the java software system. `class_name` -> The complete name of the class, for example `PathName.ClassName`. *\n\
* get_code_snippet_of_method(`method_name`) -> Get the code snippet of the java method. `method_name` -> The complete name of the java method, for example `PathName.ClassName.MethodName(ArgType1,ArgType2)`. *\n\
* exit() -> Exit function calling to give your final answer when you are confident of the answer. *\n"
                else:
                    functions = "\nFunction calls you can use are as follows.\n\
* get_code_snippet_of_method(`method_number`) -> Get the code snippet of the java method. `method_number` -> The number of the java methods suggested. *\n\
* exit() -> Exit function calling to give your final answer when you are confident of the answer.  *\n"
                    with open(f'../data/input/suspicious_methods/{dataset}/{model_name}_{rank}/{bug}.txt') as f:
                        suspicious_methods = f.read().split('\n')
                        suspicious_methods_content =  '\n'.join([f"{j}.{suspicious_methods[j-1]}" for j in range(1,len(suspicious_methods)+1)])
                        
                    input_description += f"The suggested methods are as follows:\n```\n{suspicious_methods_content}\n```\n"
                instruction = [
                    {
                        "role": "system",
                        "content": f"You are a debugging assistant of our Java software. \
You will be presented with {input_type_a} and tools (functions) to access the source code of the system under test (SUT). \
Your task is to locate the top-5 most likely culprit methods based on {input_type_the} and the information you retrieve using given functions. {functions}\
You have {max_try} chances to call function."
    },
                    {
                        "role": "user",
                        "content": f"{input_description}\
Let's locate the faulty method step by step using reasoning and function calls. \
Now reason and plan how to locate the buggy methods."
    }
                ]
                content = query(instruction)
                instruction.append({
                    "role": "Assistant",
                    "content": content
                })
                for j in range(max_try):
                    instruction.append({
                        "role": "user",
                        "content": f"Now call a function in this format `FunctionName(Argument)` in a single line without any other word."
                    })
                    content = query(instruction)
                    instruction.append({
                        "role": "Assistant",
                        "content": content
                    })
                    try:
                        function_call = content.replace("'","").replace('"','')
                        function_name = function_call[:function_call.find('(')].strip()
                        arguments = function_call[function_call.find('(')+1:function_call.rfind(')')].strip().strip('`')
                        if function_name == 'get_paths':
                            function_retval = get_paths(bug, dataset)
                        elif function_name == 'get_classes_of_path':
                            function_retval = get_classes(bug, arguments, dataset)
                        elif function_name == 'get_methods_of_class':
                            function_retval = get_methods(bug, arguments, dataset)
                        elif function_name == 'get_code_snippet_of_method':
                            if stage == 'SR':
                                function_retval = get_code_snippet(bug, arguments, dataset)
                            else:
                                function_retval = get_code_snippet(bug, suspicious_methods[int(arguments)-1], dataset)
                                function_retval = f"The code snippet of {suspicious_methods[int(arguments)-1]} is as follows.\n" + function_retval
                        elif function_name == 'find_class':
                            function_retval = find_class(bug, arguments, dataset)
                        elif function_name == 'find_method':
                            function_retval = find_method(bug, arguments, dataset)
                        elif function_name == 'exit':
                            break
                        else:
                            instruction.append({
                            "role": "user",
                            "content": "Please call functions in the right format `FunctionName(Argument)`." + functions})
                            continue
                        print(function_retval)
                        instruction.append({"role": "user", "content": function_retval})
                    except Exception as e:
                        print(e)
                        instruction.append({
                            "role": "user",
                            "content": "Please call functions in the right format `FunctionName(Argument)`." + functions})
                instruction.append({
            "role": "user",
            "content": "Based on the available information, provide complete name of the \
top-5 most likely culprit methods for the bug please. \
Since your answer will be processed automatically, please give your answer in the format as follows.\n\
Top_1 : PathName.ClassName.MethodName(ArgType1, ArgType2)\n\
Top_2 : PathName.ClassName.MethodName(ArgType1, ArgType2)\n\
Top_3 : PathName.ClassName.MethodName(ArgType1, ArgType2)\n\
Top_4 : PathName.ClassName.MethodName(ArgType1, ArgType2)\n\
Top_5 : PathName.ClassName.MethodName(ArgType1, ArgType2)\n\
"
        })
                content = query(instruction)
                instruction.append({
                        "role": "Assistant",
                        "content": content
                    })
                with open(f'../res/{output_dir}/{bug}.json', 'w') as f:
                    json.dump(instruction, f, indent=4)
                break
            except Exception as e:
                print(e)
                max_try -= 1