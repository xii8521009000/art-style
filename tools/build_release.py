"""Build a reviewable source archive from the verified Git index, never the whole folder."""
import argparse
from pathlib import Path
import zipfile
from check_public import verify,staged_bytes,ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT.parent/'art-style-source.zip')
    args=parser.parse_args()
    files=verify()
    with zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in files:archive.writestr('art-style/'+filename,staged_bytes(filename))
    print('Created verified source archive:',args.output.name)


if __name__=='__main__':main()
