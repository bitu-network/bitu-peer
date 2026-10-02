// file: src/web/internal/+/index.js
// filename: h3_utils.js



function compressCells(cells) {

    let result =
        new Set(cells);


    let changed = true;


    while (changed) {

        changed = false;


        for (
            const cell of [...result]
        ) {

            let parent =
                cell;


            while (
                h3.getResolution(parent) > 0
            ) {

                parent =
                    h3.cellToParent(
                        parent,
                        h3.getResolution(parent) - 1
                    );


                if (
                    result.has(parent)
                ) {

                    result.delete(cell);

                    changed = true;

                    break;
                }

            }

        }



        const groups =
            new Map();


        for (
            const cell of result
        ) {

            const resolution =
                h3.getResolution(cell);


            if (
                resolution === 0
            ) {
                continue;
            }


            const parent =
                h3.cellToParent(
                    cell,
                    resolution - 1
                );


            if (
                !groups.has(parent)
            ) {

                groups.set(
                    parent,
                    []
                );

            }


            groups
                .get(parent)
                .push(cell);

        }



        for (
            const [
                parent,
                children
            ]
            of groups
        ) {

            if (
                children.length === 7
            ) {

                for (
                    const child of children
                ) {

                    result.delete(
                        child
                    );

                }


                result.add(
                    parent
                );


                changed = true;

            }

        }

    }


    return result;

}





function getViewportResolution() {

    const bounds =
        map.getBounds();

    const center =
        map.getCenter();


    for (
        let r = 0;
        r <= 15;
        r++
    ) {

        const cell =
            h3.latLngToCell(
                center.lat,
                center.lng,
                r
            );


        const boundary =
            h3.cellToBoundary(
                cell
            );


        const inside =
            boundary.every(
                point =>
                    bounds.contains(
                        [
                            point[0],
                            point[1]
                        ]
                    )
            );


        if (inside) {
            return r;
        }
    }


    return 15;

}


