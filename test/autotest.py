#!/usr/bin/env python3
import messages
import argparse

def main():
    parser = argparse.ArgumentParser(description="Test messages",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--autotest", action='store_true',
                        help='Run autotest')


    subparsers = parser.add_subparsers(help='Messages subparsers')
    messages.update_subparsers(subparsers)
    args = parser.parse_args()

    print(args)
    if args.autotest:
        messages.autotest()

if __name__ == "__main__":
    main()
