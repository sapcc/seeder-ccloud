"""
 Copyright 2022 SAP SE
 
 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at
 
     http://www.apache.org/licenses/LICENSE-2.0
 
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""


import os, yaml, kopf
from argparse import ArgumentParser
from seeder_ccloud import seed_transformer

def get_yaml(file):
    with open(file, "r") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as err:
            print(err)
            raise err


def write_yaml(data, path):
    file = os.path.basename(path)
    dir = os.path.dirname(path)

    with open(os.path.join(dir, '_' + file), 'w') as f:
        yaml.dump(data.copy(), f)


def main():
    parser = ArgumentParser()
    parser.add_argument("-d", "--directory", dest="dir",
                    help="seed directory to run transform on")
    parser.add_argument("-f", "--file", dest="file",
                    help="seed file to transform")
    args = parser.parse_args()
    
    def run(file):
        patch = kopf.Patch()
        yaml_file = get_yaml(file)
        seed_transformer.transform(patch, yaml_file['spec'])
        write_yaml(patch, file)
    

    if args.file:
        run(args.file)
    else:
        assert os.path.isdir(args.dir)
        for cur_path, directories, files in os.walk(args.dir):
            for file in files:
                if '.yaml' in file:
                    run(os.path.join(cur_path, file))
            break


if __name__ == '__main__':
    main()