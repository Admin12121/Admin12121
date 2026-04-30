# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "lxml",
#     "lxml-stubs",
#     "python-dateutil",
#     "requests",
# ]
# ///
__author__ = "Admin12121"


from datetime import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
from typing import Any, Callable, Literal, TypeVar
import hashlib


T = TypeVar("T")
S = TypeVar("S")

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
GH_HEADERS = {"authorization": f"token {os.environ['ACCESS_TOKEN']}"}

USER_NAME = os.environ["USER_NAME"]
MY_ID = "U_kgDOB91p6Q"  # Admin12121
BIRTHDAY = datetime(2004, 9, 9)

QUERY_COUNT = {
    "user_getter": 0,
    "follower_getter": 0,
    "graph_repos_stars": 0,
    "recursive_loc": 0,
    "graph_commits": 0,
    "loc_query": 0,
}


def pluralise(unit: int) -> str:
    """
    Returns a properly formatted number.
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return "s" if unit != 1 else ""


def query_count(funct_id: str) -> None:
    """
    Counts how many times the GitHub GraphQL API is called.
    """
    global QUERY_COUNT

    QUERY_COUNT[funct_id] += 1


def perf_counter(func: Callable[..., S], *args: ...) -> tuple[S, float]:
    """
    Calculates the time it takes for a function to run.

    Returns the function result and the time differential.
    """
    start = time.perf_counter()
    funct_return = func(*args)

    return funct_return, time.perf_counter() - start


def formatter(
    query_type: str, difference: float, funct_return: T = False, whitespace: int = 0
) -> T | str:
    """
    Prints a formatted time differential.

    Returns formatted result if whitespace is specified, otherwise returns raw
    result.
    """
    print("{:<23}".format("   " + query_type + ":"), sep="", end="")
    print("{:>12}".format("%.4f" % difference + " s ")) if difference > 1 else print(
        "{:>12}".format("%.4f" % (difference * 1000) + " ms")
    )
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"

    return funct_return


def daily_readme(birthday: datetime) -> str:
    """
    Humanised time since birth.
    """
    diff = relativedelta.relativedelta(datetime.today(), birthday)

    return "{} {}, {} {}, {} {}{}".format(
        diff.years,
        "year" + pluralise(diff.years),
        diff.months,
        "month" + pluralise(diff.months),
        diff.days,
        "day" + pluralise(diff.days),
        " 🎂!!!" if (diff.months == 0 and diff.days == 0) else "",
    )


def simple_request(
    query: str, variables: dict[str, Any], raise_exception: bool = True
) -> requests.Response:
    """
    Returns a response, or raises an Exception if the response does not succeed.
    """
    retryable_statuses = {429, 502, 503, 504}
    attempts = 3

    for attempt in range(attempts):
        response = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers=GH_HEADERS,
        )
        if response.status_code == 200:
            return response

        if response.status_code not in retryable_statuses or attempt == attempts - 1:
            if raise_exception:
                raise Exception(
                    f"Failed with a {response.status_code}: {response.text}, {QUERY_COUNT}"
                )
            return response

        time.sleep(1 << attempt)


def graph_commits(start_date: datetime, end_date: datetime) -> int:
    """
    Uses GitHub's GraphQL v4 API to return my total commit count.
    """
    query_count("graph_commits")
    query = """
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }"""
    variables = {"start_date": start_date, "end_date": end_date, "login": USER_NAME}
    response = simple_request(query, variables)

    return int(
        response.json()["data"]["user"]["contributionsCollection"][
            "contributionCalendar"
        ]["totalContributions"]
    )


def graph_repos_stars(
    count_type: Literal["repos", "stars", "loc"],
    owner_affiliation: list[str],
    cursor: int | None = None,
) -> int:
    """
    Uses GitHub's GraphQL v4 API to return my total repository, star, or lines
    of code count.
    """
    query_count("graph_repos_stars")
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }"""
    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor,
    }
    request = simple_request(query, variables)
    if request.status_code == 200:
        if count_type == "repos":
            return request.json()["data"]["user"]["repositories"]["totalCount"]
        elif count_type == "stars":
            return stars_counter(
                request.json()["data"]["user"]["repositories"]["edges"]
            )

    return 0


def loc_counter_one_repo(
    owner: str,
    repo_name: str,
    data: list[str],
    cache_comment: list[str],
    history: dict[str, Any],
    addition_total: int,
    deletion_total: int,
    my_commits: int,
) -> tuple[int, int, int]:
    """
    Recursively call recursive_loc (since GraphQL can only search 100 commits at
    a time) only adds the LOC value of commits authored by me.
    """
    for node in history["edges"]:
        if node["node"]["author"]["user"] == owner_id:
            my_commits += 1
            addition_total += node["node"]["additions"]
            deletion_total += node["node"]["deletions"]

    if history["edges"] == [] or not history["pageInfo"]["hasNextPage"]:
        return addition_total, deletion_total, my_commits
    else:
        return recursive_loc(
            owner,
            repo_name,
            data,
            cache_comment,
            addition_total,
            deletion_total,
            my_commits,
            history["pageInfo"]["endCursor"],
        )


def recursive_loc(
    owner: str,
    repo_name: str,
    data: list[str],
    cache_comment: list[str],
    addition_total: int = 0,
    deletion_total: int = 0,
    my_commits: int = 0,
    cursor: str | None = None,
) -> tuple[int, int, int]:
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch 100 commits from
    a repository at a time.
    """
    query_count("recursive_loc")
    query = """
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }"""
    variables = {"repo_name": repo_name, "owner": owner, "cursor": cursor}
    request = simple_request(query, variables, raise_exception=False)
    if request.status_code == 200:
        if (
            request.json()["data"]["repository"]["defaultBranchRef"] is not None
        ):  # Only count commits if repo isn't empty
            return loc_counter_one_repo(
                owner,
                repo_name,
                data,
                cache_comment,
                request.json()["data"]["repository"]["defaultBranchRef"]["target"][
                    "history"
                ],
                addition_total,
                deletion_total,
                my_commits,
            )
        else:
            return 0, 0, 0

    force_close_file(
        data, cache_comment
    )  # saves what is currently in the file before this program crashes

    if request.status_code == 403:
        raise Exception(
            "Too many requests in a short amount of time!\nYou've hit the non-documented anti-abuse limit!"
        )

    raise Exception(
        "recursive_loc() has failed with a",
        request.status_code,
        request.text,
        QUERY_COUNT,
    )


def cache_builder(
    edges: list[dict[str, Any]],
    comment_size: int,
    force_cache: bool,
    loc_add: int = 0,
    loc_del: int = 0,
) -> tuple[int, int, int, bool]:
    """
    Checks each repository in edges to see if it has been updated since the last
    time it was cached.

    If it has, run recursive_loc on that repository to update the LOC count.
    """
    cached = True  # Assume all repositories are cached
    filename = f"cache/{hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()}.txt"  # Create a unique filename for each user
    try:
        with open(filename, "r") as f:
            data = f.readlines()
    except FileNotFoundError:  # If the cache file doesn't exist, create it
        data = []
        if comment_size > 0:
            for _ in range(comment_size):
                data.append(
                    "This line is a comment block. Write whatever you want here.\n"
                )

        with open(filename, "w") as f:
            f.writelines(data)

    if (
        len(data) - comment_size != len(edges) or force_cache
    ):  # If the number of repos has changed, or force_cache is True
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, "r") as f:
            data = f.readlines()

    cache_comment = data[:comment_size]  # save the comment block
    data = data[comment_size:]  # remove those lines
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if (
            repo_hash
            == hashlib.sha256(
                edges[index]["node"]["nameWithOwner"].encode("utf-8")
            ).hexdigest()
        ):
            try:
                if (
                    int(commit_count)
                    != edges[index]["node"]["defaultBranchRef"]["target"]["history"][
                        "totalCount"
                    ]
                ):
                    # if commit count has changed, update loc for that repo
                    owner, repo_name = edges[index]["node"]["nameWithOwner"].split("/")
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = (
                        repo_hash
                        + " "
                        + str(
                            edges[index]["node"]["defaultBranchRef"]["target"][
                                "history"
                            ]["totalCount"]
                        )
                        + " "
                        + str(loc[2])
                        + " "
                        + str(loc[0])
                        + " "
                        + str(loc[1])
                        + "\n"
                    )
            except TypeError:  # If the repo is empty
                data[index] = repo_hash + " 0 0 0 0\n"
    with open(filename, "w") as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])

    return loc_add, loc_del, loc_add - loc_del, cached


def loc_query(
    owner_affiliation: list[str],
    comment_size: int = 0,
    force_cache: bool = False,
    cursor: int | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> tuple[int, int, int, bool]:
    query_count("loc_query")
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }"""
    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor,
    }
    request = simple_request(query, variables)

    if edges is None:
        edges = []

    if request.json()["data"]["user"]["repositories"]["pageInfo"][
        "hasNextPage"
    ]:  # If repository data has another page
        edges += request.json()["data"]["user"]["repositories"][
            "edges"
        ]  # Add on to the LoC count
        return loc_query(
            owner_affiliation,
            comment_size,
            force_cache,
            request.json()["data"]["user"]["repositories"]["pageInfo"]["endCursor"],
            edges,
        )
    else:
        total_edges = edges + request.json()["data"]["user"]["repositories"]["edges"]

        return cache_builder(total_edges, comment_size, force_cache)


def flush_cache(edges: list[dict[str, Any]], filename: str, comment_size: int) -> None:
    """
    Wipes the cache file.

    This is called when the number of repositories changes or when the file is
    first created.
    """
    with open(filename, "r") as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size]  # only save the comment

    with open(filename, "w") as f:
        f.writelines(data)
        for node in edges:
            f.write(
                hashlib.sha256(
                    node["node"]["nameWithOwner"].encode("utf-8")
                ).hexdigest()
                + " 0 0 0 0\n"
            )


def add_archive() -> tuple[int, int, int, int, int]:
    """
    Several repositories I have contributed to have since been deleted.

    This function adds them using their last known data.
    """
    with open("repository_archive.txt", "r") as f:
        data = f.readlines()

    old_data = data
    data = data[7 : len(data) - 3]  # remove the comment block
    added_loc, deleted_loc, added_commits = 0, 0, 0
    contributed_repos = len(data)
    for line in data:
        repo_hash, total_commits, my_commits, *loc = line.split()
        added_loc += int(loc[0])
        deleted_loc += int(loc[1])
        if my_commits.isdigit():
            added_commits += int(my_commits)

    if old_data == []:
        return (0, 0, 0, 0, 0)

    added_commits += int(old_data[-1].split()[4][:-1])

    return (
        added_loc,
        deleted_loc,
        added_loc - deleted_loc,
        added_commits,
        contributed_repos,
    )


def force_close_file(data: list[str], cache_comment: list[str]) -> None:
    """
    Forces the file to close, preserving whatever data was written to it.

    This is needed because if this function is called, the program would've
    crashed before the file is properly saved and closed.
    """
    filename = "cache/" + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest() + ".txt"
    with open(filename, "w") as f:
        f.writelines(cache_comment)
        f.writelines(data)

    print(
        "There was an error while writing to the cache file. The file,",
        filename,
        "has had the partial data saved and closed.",
    )


def stars_counter(data: list[dict[str, Any]]) -> int:
    """
    Count total stars in repositories owned by me.
    """
    total_stars = 0
    for node in data:
        total_stars += node["node"]["stargazers"]["totalCount"]

    return total_stars


def svg_overwrite(
    filename: str,
    age_data: str,
    commit_data: int,
    star_data: int,
    repo_data: int,
    contrib_data: int,
    follower_data: int,
    loc_data: tuple[int, int, int],
    pr_data: int,
    issue_data: int,
) -> None:
    """
    Parse SVG files and update elements with my age, commits, stars,
    repositories, pull requests, issues, and lines written.
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, "age_data", age_data, 49)
    justify_format(root, "commit_data", commit_data, 22)
    justify_format(root, "star_data", star_data, 14)
    justify_format(root, "repo_data", repo_data, 7)
    justify_format(root, "contrib_data", contrib_data)
    justify_format(root, "follower_data", follower_data, 10)
    justify_format(root, "loc_data", loc_data[2], 9)
    justify_format(root, "loc_add", loc_data[0])
    justify_format(root, "loc_del", loc_data[1], 7)
    justify_format(root, "pr_data", pr_data, 17)
    justify_format(root, "issue_data", issue_data, 13)
    tree.write(filename, encoding="utf-8", xml_declaration=True)


def justify_format(
    root: etree.ElementBase, element_id: str, new_text: int | str, length: int = 0
) -> None:
    """
    Updates and formats the text of the element, and modifes the amount of dots
    in the previous element to justify the new text on the svg.
    """
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: "", 1: " ", 2: ". "}
        dot_string = dot_map[just_len]
    else:
        dot_string = " " + ("." * just_len) + " "
    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root: etree.ElementBase, element_id: str, new_text: str) -> None:
    """
    Finds the element in the SVG file and replaces its text with a new value
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def commit_counter(comment_size: int) -> int:
    """
    Counts up my total commits, using the cache file created by cache_builder.
    """
    total_commits = 0
    filename = (
        "cache/" + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest() + ".txt"
    )  # Use the same filename as cache_builder
    with open(filename, "r") as f:
        data = f.readlines()

    cache_comment = data[:comment_size]  # save the comment block

    data = data[comment_size:]  # remove those lines
    for line in data:
        total_commits += int(line.split()[2])

    return total_commits


def user_getter(username: str) -> tuple[dict[str, str], str]:
    """
    Returns the account ID and creation time of the user
    """
    query_count("user_getter")
    query = """
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }"""
    variables = {"login": username}
    request = simple_request(query, variables)

    return {"id": request.json()["data"]["user"]["id"]}, request.json()["data"]["user"][
        "createdAt"
    ]


def follower_getter(username: str) -> int:
    """
    Returns the number of followers of the user
    """
    query_count("follower_getter")
    query = """
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }"""
    request = simple_request(query, {"login": username})

    return int(request.json()["data"]["user"]["followers"]["totalCount"])


def _iter_paginated_rest(
    url: str, headers: dict[str, str], session: requests.Session | None = None
) -> list[dict[str, Any]]:
    """Iterate through paginated GitHub REST API responses using Link header."""
    if session is None:
        session = requests.Session()

    results = []
    current_url: str | None = url
    while current_url:
        response = session.get(current_url, headers=headers)
        response.raise_for_status()

        data = response.json()
        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict) and "items" in data:
            # Search API returns results wrapped in "items"
            results.extend(data["items"])
        else:
            raise RuntimeError(f"Unexpected response format: {type(data)}")

        # Parse Link header for next page
        link_header = response.headers.get("Link", "")
        current_url = None
        if link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    current_url = part.split(";")[0].strip("<> ")
                    break

    return results


def get_pull_requests(
    owner: str, repo: str, state: str = "open"
) -> list[dict[str, Any]]:
    """Fetch all pull requests for a repository using clean pagination."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/pulls?state={state}&per_page=100"
    )
    session = requests.Session()
    return _iter_paginated_rest(url, GH_HEADERS, session)


def get_issues(owner: str, repo: str, state: str = "open") -> list[dict[str, Any]]:
    """Fetch all issues for a repository, excluding pull requests."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/issues?state={state}&per_page=100"
    )
    session = requests.Session()
    all_items = _iter_paginated_rest(url, GH_HEADERS, session)

    # Filter out pull requests (they have a 'pull_request' key)
    return [item for item in all_items if "pull_request" not in item]


def get_pr_issue_counts() -> tuple[int, int]:
    """Get total PR and issue counts across ALL repositories (including orgs)."""
    try:
        session = requests.Session()

        # Use GitHub search API to find ALL PRs authored by you (including in orgs)
        pr_search_url = f"https://api.github.com/search/issues?q=type:pr+author:{USER_NAME}&per_page=100"
        pr_results = _iter_paginated_rest(pr_search_url, GH_HEADERS, session)
        pr_count = len(pr_results)

        # Use GitHub search API to find ALL issues authored by you (including in orgs)
        issue_search_url = f"https://api.github.com/search/issues?q=type:issue+author:{USER_NAME}&per_page=100"
        issue_results = _iter_paginated_rest(issue_search_url, GH_HEADERS, session)
        issue_count = len(issue_results)

        return pr_count, issue_count

    except Exception as e:
        print(f"Warning: Could not fetch PR/issue data: {e}")
        return 0, 0


if __name__ == "__main__":
    print("Calculation times:")
    # define global variable for owner ID and calculate user's creation date
    user_data, user_time = perf_counter(user_getter, USER_NAME)
    owner_id, acc_date = user_data
    formatter("account data", user_time)
    age_data, age_time = perf_counter(daily_readme, BIRTHDAY)
    formatter("age calculation", age_time)
    total_loc, loc_time = perf_counter(
        loc_query, ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"], 7
    )
    formatter("LOC (cached)", loc_time) if total_loc[-1] else formatter(
        "LOC (no cache)", loc_time
    )
    commit_data, commit_time = perf_counter(commit_counter, 7)
    star_data, star_time = perf_counter(graph_repos_stars, "stars", ["OWNER"])
    repo_data, repo_time = perf_counter(graph_repos_stars, "repos", ["OWNER"])
    contrib_data, contrib_time = perf_counter(
        graph_repos_stars, "repos", ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]
    )
    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)

    # Get PR and issue counts with performance timing
    pr_issue_data, pr_issue_time = perf_counter(get_pr_issue_counts)
    pr_count, issue_count = pr_issue_data
    formatter("PR/issue counts", pr_issue_time)

    # several repositories that I've contributed to have since been deleted.
    if owner_id == {"id": MY_ID}:  # only calculate for user PenguinDevs
        archived_data = add_archive()
        total_loc = list(total_loc)
        for index in range(len(total_loc) - 1):
            total_loc[index] += archived_data[index]
        contrib_data += archived_data[-1]
        commit_data += int(archived_data[-2])

    # Store the unformatted values for svg_overwrite
    loc_data_tuple = (total_loc[0], total_loc[1], total_loc[2])

    for index in range(len(total_loc) - 1):
        total_loc[index] = "{:,}".format(
            total_loc[index]
        )  # format added, deleted, and total LOC

    svg_overwrite(
        "dark-mode.svg",
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        loc_data_tuple,
        pr_count,
        issue_count,
    )
    svg_overwrite(
        "light-mode.svg",
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        loc_data_tuple,
        pr_count,
        issue_count,
    )

    # move cursor to override 'Calculation times:' with 'Total function time:' and the total function time, then move cursor back
    print(
        "\033[F\033[F\033[F\033[F\033[F\033[F\033[F\033[F",
        "{:<21}".format("Total function time:"),
        "{:>11}".format(
            "%.4f"
            % (
                user_time
                + age_time
                + loc_time
                + commit_time
                + star_time
                + repo_time
                + contrib_time
                + follower_time
                + pr_issue_time
            )
        ),
        " s \033[E\033[E\033[E\033[E\033[E\033[E\033[E\033[E",
        sep="",
    )

    print("Total GitHub GraphQL API calls:", "{:>3}".format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items():
        print("{:<28}".format("   " + funct_name + ":"), "{:>6}".format(count))
