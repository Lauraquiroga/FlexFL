import json
import os
from function_call import get_code_snippet
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='Defects4J', choices=['Defects4J','GHRB'])
    parser.add_argument('--bug_list', default='All', choices=['All','AutoFL'])
    parser.add_argument('--model', default='Llama3') #choices=['Llama3', 'Qwen2', 'Mistral']
    parser.add_argument('--stage', default='LR', choices=['SR','LR'])
    parser.add_argument('--results_dir', default=None)
    args = parser.parse_args()
    dataset = args.dataset
    model = args.model
    stage = args.stage

    if args.results_dir:
        results_dir = args.results_dir
    elif stage == 'LR':
        results_dir = f'../res/{model}_{dataset}_All'
    else:
        results_dir = f'../res/{model}_{dataset}_SR'

    if args.bug_list == 'All':
        with open(f'../data/bug_list/{dataset}/bug_list.txt') as f: #to test a different list of bugs update file
            bugs = [e.strip() for e in f.readlines()]
    elif args.bug_list == 'AutoFL':
        with open(f'../data/bug_list/{dataset}/bug_list_AutoFL.txt') as f:
            bugs = [e.strip() for e in f.readlines()]

    with open(f'../data/input/ground_truth/{dataset}/gt.json') as f:
        gt = json.load(f)

    top1_cnt = 0
    top1 = []
    top3_cnt = 0
    top3 = []
    top5_cnt = 0
    top5 = []
    bug_cnt = 0

    MAP = 0
    MRR = 0

    for bug in bugs:
        if not os.path.exists(f'{results_dir}/{bug}.json'):
            res = [{"content":""}]
        else:
            with open(f'{results_dir}/{bug}.json') as f:
                res = json.load(f)

        bug_cnt += 1
        res = res[-1]['content']
        suspicious_methods = []
        for line in res.split('\n'):
            for i in range(1,6):
                if f'Top_{i} : ' in line:
                    suspicious_methods.append(line.split(f'Top_{i} : ')[1].strip())
                elif f'Top_{i}: ' in line:
                    suspicious_methods.append(line.split(f'Top_{i}: ')[1].strip())
                elif f'Top {i}: ' in line:
                    suspicious_methods.append(line.split(f'Top {i}: ')[1].strip())
        for i in [1,3,5]:
            flag = False
            for method in suspicious_methods[:i]:
                method = method.replace(', ',',')
                method = method.replace(' ,',',')
                code = get_code_snippet(bug, method, dataset)
                if code.startswith('Do you'):
                    method = code.split('`')[1]
                elif code.startswith('You') and '\n' in code:
                    method = code.split('\n')[1]
                if method in gt[bug]:
                    flag = True
                    break

            if flag:
                if i == 1: 
                    top1_cnt += 1
                    top1.append(bug)
                if i == 3: 
                    top3_cnt += 1
                    top3.append(bug)
                if i == 5: 
                    top5_cnt += 1
                    top5.append(bug)
        for i in range(min(5,len(suspicious_methods))):
            method = suspicious_methods[i]
            method = method.replace(', ',',')
            method = method.replace(' ,',',')
            code = get_code_snippet(bug, method, dataset)
            if code.startswith('Do you'):
                method = code.split('`')[1]
            elif code.startswith('You') and '\n' in code:
                method = code.split('\n')[1]
            if method in gt[bug]:
                MRR += 1 / (i+1)
                break
        avg_pre = 0
        for gt_method in gt[bug]:
            num = 0
            for i in range(min(5,len(suspicious_methods))):
                method = suspicious_methods[i]
                method = method.replace(', ',',')
                method = method.replace(' ,',',')
                code = get_code_snippet(bug, method, dataset)
                if code.startswith('Do you'):
                    method = code.split('`')[1]
                elif code.startswith('You') and '\n' in code:
                    method = code.split('\n')[1]
                if method in gt[bug]:
                    num += 1
                if method == gt_method:
                    precision = num / (i+1)
                    avg_pre += precision
                    break
        if len(gt[bug]) != 0:
            avg_pre /= len(gt[bug])
        MAP += avg_pre
    if args.results_dir:
        print(f"Results of {results_dir}:")
    else:
        print(f"Results of {model}+{dataset}+{stage}:")
    print("Top-1", top1_cnt)
    print("Top-3", top3_cnt)
    print("Top-5", top5_cnt)
    print("All", bug_cnt)
    print("MAP", MAP / bug_cnt)
    print("MRR", MRR / bug_cnt)
    # res = {
    #     "Total": bug_cnt,
    #     "Top-1": top1_cnt,
    #     "Top-3": top3_cnt,
    #     "Top-5": top5_cnt,
    #     "MAP": MAP / bug_cnt,
    #     "MRR": MRR / bug_cnt,
    #     "top-1": top1,
    #     "top-3": top3,
    #     "top-5": top5
    # }
    # with open(f'./res.json', 'w') as f:
    #     json.dump(res,f,indent=4)