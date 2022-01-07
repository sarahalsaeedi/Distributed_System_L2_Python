

Task 1 – Leader Election:

	1.1- The leader Election algorithm is the Ring algorithm used in our implementation.


Task 2 – Centralized Blackboard:
	2.1- All requests are processed through the elected leader as a centralized solution.
	2.2- Order is the same on all servers tested on all.
	2.3- Concurrent modify is not breaking the consistency.


Task 3 – Argue for your choices:
	3.1- File attached as docx file


Optional Task A – Network Dynamicity:
	1- The leader set to be failed within 40 seconds (you can adjust it), any request forwarded to the leader
 	(you will have to do post request from any request!), the requester server will noted that the server is
 	down and server# will initiate an election request circulated through the network.

	2- During the election if the node can't reach its successor it will send it to the next node by 
	using python itertools.cycle.


# Please Run the Corner Cases Presentation Ibrahim_ Sarah.pptx will explain the problems as animation view
