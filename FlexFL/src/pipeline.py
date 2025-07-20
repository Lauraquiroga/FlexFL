from typing import List, Optional #List: generic list type, Optional: A variable can be its type or None
from llama import Dialog, Llama #in the llama folder inside Meta's llama3 repository, the script generation.py defines the class Llama (for inference) and Dialog (used to structure chat messages).
import torch.distributed as dist

import json
import os
from function_call import get_code_snippet, get_paths, get_classes, get_methods, find_class, find_method
import argparse #command-line argument parsing (to pass flags)

# Construction of open-source model
model_name = 'Llama3'
######################### START

# 1. Build
ckpt_dir: str = 'Meta-Llama-3-8B-Instruct/' #Path to the directory containing checkpoint files (LLaMA model weights).
tokenizer_path: str = 'Meta-Llama-3-8B-Instruct/tokenizer.model' #Path to the tokenizer used to encode/decode text for the model.
temperature: float = 0 #Makes the model deterministic
top_p: float = 1.0 #Controls randomness. 1.0 means consider all tokens

# Note: for Repetition Strategy set temperature=0.6 and top_p=0.9

seed = 42
max_seq_len: int = 8192 #Maximum sequence length for input text.
max_batch_size: int = 1 #Maximum batch size for inference.
max_gen_len: Optional[int] = None

#Build a Llama instance by initializing and loading a pre-trained model.
generator = Llama.build(
        ckpt_dir=ckpt_dir,
        tokenizer_path=tokenizer_path,
        max_seq_len=max_seq_len,
        max_batch_size=max_batch_size,
        seed=seed, 
    )

# 2. Inference
def query(instruction):
    """
    Submits a chat-based prompt to the model and returns the output string
    (main way the script interacts with the LLM)
    """
    results = generator.chat_completion(
                        [instruction],
                        max_gen_len=max_gen_len,
                        temperature=temperature,
                        top_p=top_p,
                    )
    result = results[0]
    print(f"> {result['generation']['role'].capitalize()}: {result['generation']['content']}")
    content = result['generation']['content'].strip()
    return content

######################### END

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='Defects4J', choices=['Defects4J', 'GHRB'])
    parser.add_argument('--input', default='All', choices=['bug_report', 'trigger_test', 'All'])
    parser.add_argument('--stage', default='SR', choices=['SR', 'LR'])
    parser.add_argument('--rank', default='All')
    args = parser.parse_args()
    dataset = args.dataset
    input_type = args.input
    stage = args.stage
    rank = args.rank

    # Loads the list of bug IDs to be analyzed (e.g., Time-25)
    with open(f'../data/bug_list/{dataset}/bug_list.txt') as f:
        bugs = [e.strip() for e in f.readlines()]

    # Creates output directory for Space Reduction stage
    if stage == 'SR':
        output_dir = f"{model_name}_{dataset}_SR" + ("_br" if input_type == 'bug_report' else "") + ("_tt" if input_type == 'trigger_test' else "")
    else: # Creates output directory for final results (Localization Refinement Stage)
        output_dir = f"{model_name}_{dataset}_{rank}"

    # os.system(f'rm -rf ../res/{output_dir}')
    # os.system(f'mkdir ../res/{output_dir}')
    
    #Just create the folder if it doesn't exist (no deletion)
    os.makedirs(f'../res/{output_dir}', exist_ok=True)
    
    for bug in bugs:
        if bug != 'Time-25': # To run only for 1 bug: Time-25
            continue
        print(bug)
        max_try = 10 #Initial value of MAX as mentioned in paper
        while max_try > 0:
            try:
                # Dynamic construction of the query:

                ##FIRST: Depending on input type, set input_type_a, input_type_the and input_description vars

                #1. In case there is a bug report: (Both input types or only bug reports)
                input_description = ""
                if (input_type == 'All' or input_type =='bug_report') and os.path.exists(f'../data/input/bug_reports/{dataset}/{bug}.json'):
                    input_type_a = "a bug report"
                    with open(f'../data/input/bug_reports/{dataset}/{bug}.json') as f:
                        bug_report = json.load(f)
                        if dataset == 'Defects4J':
                            input_description += f"The bug report is as follows:\n```\nTitle:{bug_report['title']}\nDescription:{bug_report['description']}\n```\n"
                        else:
                            input_description += f"The bug report is as follows:\n```\nTitle:{bug_report['title']}\nDescription:{bug_report['description_text']}\n```\n"
                else: #If there are is bug report
                    input_type_a = None

                #2. In case there are trigger tests: (Both input types or only trigger tests)
                if (input_type == 'All' or input_type =='trigger_test') and os.path.exists(f'../data/input/trigger_tests/{dataset}/{bug}.txt'):
                    if input_type_a:
                        input_type_a += ", a trigger test"
                    else:
                        input_type_a = "a trigger test"
                    with open(f'../data/input/trigger_tests/{dataset}/{bug}.txt') as f:
                        trigger_test = f.read()
                        input_description += f"The trigger test is as follows:\n```\n{trigger_test}\n```\n"


                input_type_the = input_type_a.replace('a', 'the')

                ##SECOND: Based on stage, set functions (defined in function_call.py) and update input_description

                #3. If we are doing Space Reduction (Agent4SR) -> can use the following functions to explore the code
                if stage == 'SR':
                    functions = "\nFunction calls you can use are as follows.\n\
* find_class(`class_name`) -> Find a class in the bug report by fuzzy search. `class_name` -> The name of the class. *\n\
* find_method(`method_name`) -> Find a method in the bug report by fuzzy search. `method_name` -> The name of the method. *\n\
* get_paths() -> Get the paths of the java software system. *\n\
* get_classes_of_path(`path_name`) -> Get the classes in the path of the java software system. `path_name` -> The accurate name of the path which can be accessed by function call `get_paths`. *\n\
* get_methods_of_class(`class_name`) -> Get the methods belonging to the class of the java software system. `class_name` -> The complete name of the class, for example `PathName.ClassName`. *\n\
* get_code_snippet_of_method(`method_name`) -> Get the code snippet of the java method. `method_name` -> The complete name of the java method, for example `PathName.ClassName.MethodName(ArgType1,ArgType2)`. *\n\
* exit() -> Exit function calling to give your final answer when you are confident of the answer. *\n"

                #4. If we are doing Localization Refinement (Agent4LR) -> can only use get_code_snippet_of_method to explore candidates
                # Uses suspicious method list to update the input description
                else:
                    functions = "\nFunction calls you can use are as follows.\n\
* get_code_snippet_of_method(`method_number`) -> Get the code snippet of the java method. `method_number` -> The number of the java methods suggested. *\n\
* exit() -> Exit function calling to give your final answer when you are confident of the answer.  *\n"
                    with open(f'../data/input/suspicious_methods/{dataset}/{model_name}_{rank}/{bug}.txt') as f:
                        suspicious_methods = f.read().split('\n')
                        suspicious_methods_content =  '\n'.join([f"{j}.{suspicious_methods[j-1]}" for j in range(1,len(suspicious_methods)+1)])
                        
                    input_description += f"The suggested methods are as follows:\n```\n{suspicious_methods_content}\n```\n"

                ##THIRD: Putting together the instruction
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
                content = query(instruction) #Instruction is submitted to llm and response is saved in content
                instruction.append({
                    "role": "Assistant",
                    "content": content
                })
                for j in range(max_try): ##FOUTRH: Nested for ->Function calling
                    instruction.append({
                        "role": "user",
                        "content": f"Now call a function in this format `FunctionName(Argument)` in a single line without any other word."
                    })
                    content = query(instruction)
                    instruction.append({
                        "role": "Assistant",
                        "content": content
                    })
                    try: #Function calling using code from function_call.py (Table II paper)
                        function_call = content.replace("'","").replace('"','') #remove quotation marks
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
                content = query(instruction) #Instruction is submitted to llm and response is saved in content
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