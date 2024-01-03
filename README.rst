.. sectnum::
.. contents::

Multiprocessing and Configuration Utils
=======================================

Utility classes and functions for managing `cross-cutting concerns <https://en.wikipedia.org/wiki/Cross-cutting_concern>`_ in Python applications that use multiprocessing.

Background and Overview
-----------------------

Need for the multiprocessing module
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The standard ("reference implementation") Python interpreter, CPython, sidesteps many of the complexities associated with concurrency by imposing a so-called `Global Interpreter Lock <https://wiki.python.org/moin/GlobalInterpreterLock>`_ on Python objects and bytecode.  While this allows a limited form of *threading* (`"cooperative multitasking" <https://en.wikipedia.org/wiki/Cooperative_multitasking>`_), it effectively prevents single-process Python applications from achieving true **parallelism**.

Computation-heavy applications requiring parallel execution are therefore required to use one of the following approaches:
- bypassing the GIL entirely using C or Cython extension modules;
  - this is the approach taken by many (all?) standard numerical libraries, such as ``numpy``, ``pandas``, ``tensorflow``, etc.
- using components written in other languages to manage the core computations;
- delegating computational work to sub-interpreters running in **subprocesses** using Python's ``multiprocessing`` module.  This is the preferred approach for most applications.

.. The ``multiprocessing`` module provides an API superficially similar to the ``threading`` module, which is both convenient and a source of confusion.

Shortcomings of MP
^^^^^^^^^^^^^^^^^^

Unfortunately, using ``multiprocessing`` in Python can significantly increase both the complexity and bug count of an application, particularly when the application needs to use ``threading`` to manage IO-bound operations.

The reasons for this mostly have to do with shortcomings in OS-level implementations of system calls like *fork* (Linux) and *spawn* (Linux, Windows).  For instance:
- It is `not possible to use threads in a fork-safe manner <https://stackoverflow.com/a/46440564>`_
- Database clients provided by libraries like ``PyMongo`` are frequently `not fork-safe <https://pymongo.readthedocs.io/en/stable/faq.html>`_
- File IO becomes much more complicated when multiple processes need access to a file (or any other resource, for that matter).  For example, the `Python logging cookbook <https://docs.python.org/3/howto/logging-cookbook.html>`_ provides several sections discussing the need to delegate logging IO from worker processes to a single "manager" process; see `this section <https://docs.python.org/3/howto/logging-cookbook.html#logging-to-a-single-file-from-multiple-processes>`_ for an example.

The upshot of these shortcomings is that any **cross-cutting concerns**--that is, any aspects of app functionality that need to be shared by or accessible to all application processes and subprocesses--must be implemented with great care, and should be thoroughly tested for concurrency-related bugs.

Workarounds
^^^^^^^^^^^

The Python ecosystem offers many workarounds and "canned" solutions to the problems listed above (for examples, just look for StackOverflow threads related to "Python" and "multiprocessing").  Some of the more useful include:
- Control over precisely how the OS is used to produce subprocesses.
  - Natively, Linux supports two "modes" of child process generation: *fork* and *spawn*.  The ``multiprocessing`` module effectively adds a third API, called *forkserver*, that maintains a controlled state from which subprocesses should be forked
- Shared memory "blobs" which can be accessed by multiple processes without using locks or semaphores
- *Proxies* that can expose a controlled subset of a shared object's functionality
- Socket-based servers can be used to manage multiprocessing IO in long-running or clustered applications

Goals
-----

This project aims to consolidate tools and utility functions for interacting with multiple subprocesses in a safe and consistent way.

Specifically, the goal is to provide a consistent API for setting up the following:
- logging from multiple processes
  - this should support logging to shared streams (stdout, stderr), shared files, shared DBs, or whatever else is needed
- shared configuration
  - the eventual goal is to incorporate a full dependency injection framework, such as `Python dependency injector <https://python-dependency-injector.ets-labs.org/>`_
  - for now, configuration management will take the form of a shared ``dict`` or ``dict`` proxy controlled by a server process
- worker process management
  - workers should always be forked from a singleton *forkserver*, with access to the same set of shared configuration
- data and file IO
  - database access should be abstracted behind a shared interface in order to prevent incorrect usage
